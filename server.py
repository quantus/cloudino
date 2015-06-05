import json
import sys
import os
from random import randint
import time
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict
import tornado.ioloop
import tornado.web
from tornado import gen, websocket
from tornado.tcpserver import TCPServer
from sqlalchemy import (
    create_engine,
    Column,
    Boolean,
    Integer,
    String,
    DateTime,
    ForeignKey,
    desc
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    scoped_session,
    sessionmaker,
    relationship
)
Base = declarative_base()

engine = create_engine(os.environ.get(
    'DATABASE_URI',
    'postgresql+pypostgresql://localhost/cloudino'
))

session = scoped_session(sessionmaker(bind=engine))()


class Device(Base):
    __tablename__ = 'device'
    id = Column(Integer, primary_key=True)
    device_name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    device_secret = Column(String, nullable=False)

    measurements = relationship('Measurement', backref='device')


class Measurement(Base):
    __tablename__ = 'measurement'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('device.id'))
    ip_address = Column(String, nullable=False)
    measurement_name = Column(String, nullable=False)
    measurement_value = Column(Integer, nullable=False)
    measurement_type = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    authority = Column(Boolean, nullable=False, default=False)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render(
            "real_index.html",
            devices=session.query(Device).all(),
            connections=connections
        )


class ViewHandler(tornado.web.RequestHandler):
    def get(self):
        failure_ids = map(int, self.request.arguments.get('failure', []))
        failures = session.query(Device).filter(Device.id.in_(failure_ids)).all() if failure_ids else []
        device_ids = self.request.arguments.get('id', [])
        device_ids = list(set(map(int, device_ids)))
        if not device_ids:
            self.redirect('/')
            return
        all_inputs = (
            session.query(Measurement)
            .filter(
                Measurement.measurement_type == 'input',
                Measurement.device_id.in_(device_ids)
            )
            .order_by(Measurement.device_id, Measurement.id)
            .all()
        )
        inputs = {
            name: [input for input in all_inputs if input.measurement_name == name]
            for name in set([i.measurement_name for i in all_inputs])
        }
        events = (
            session.query(Measurement)
            .filter(
                Measurement.measurement_type.in_(['event', 'input']),
                Measurement.device_id.in_(device_ids)
            )
            .order_by(Measurement.timestamp)
        ).all()
        measurement_names = {i[0] for i in (
            session.query(Measurement.measurement_name)
            .filter(
                Measurement.measurement_type == 'measurement',
                Measurement.device_id.in_(device_ids)
            )
            .order_by(Measurement.timestamp)
        ).all()
        }

        start_date = (datetime.now() - timedelta(days=14)).date()
        end_date = datetime.now()  # .date()

        measurements = OrderedDict()
        for m in measurement_names:
            measurements[m] = (
                [(i[0], i[1], i[2]) for i in session.execute(
                    '''
WITH t AS (
   SELECT ts
   FROM   generate_series('%s', '%s', '15 minute'::interval) ts
   )
SELECT
    ts,
    device_id,
    AVG(measurement_value)
FROM t
LEFT JOIN measurement ON
    date_trunc('hour', timestamp) = date_trunc('hour', ts) AND
    (extract(minute from timestamp)::int/15) = (extract(minute from ts)::int/15) AND
    measurement_name = '%s' AND
    measurement_type = 'measurement'
WHERE device_id IN (%s) OR device_id IS NULL
GROUP BY 1, 2
ORDER BY 1, 2
                    ''' % (start_date, end_date, m, ','.join(map(str,device_ids)))
                ).fetchall()]
            )

        measurements2 = OrderedDict()
        for k in measurements:
            handled_device_ids = set()
            devices = []
            data = measurements[k]
            data2 = OrderedDict()
            for time, device, value in data:
                if not time in data2:
                    data2[time] = OrderedDict()
                data2[time][device] = value
                if device and device not in handled_device_ids:
                    handled_device_ids.update([device])
                    devices.append(session.query(Device).get(device))
            measurements2[k] = (devices, data2)

        csvs = OrderedDict()
        for graph_name in measurements2:
            devices, m_data = measurements2[graph_name]
            msg = "'Date,{}\\n'".format(','.join(d.device_name for d in devices))
            for t, data in m_data.items():
                msg += "\n + '{},{}\\n'".format(t, ','.join(str(data.get(d.id,'')) for d in devices))
            csvs[graph_name] = msg

        # import pudb;pu.db
        self.render(
            "view_devices.html",
            devices=session.query(Device).filter(Device.id.in_(device_ids)).all(),
            connections=connections,
            inputs=inputs,
            events=events,
            measurements=measurements2,
            csvs=csvs,
            failures=failures
        )

    @gen.coroutine
    @tornado.web.asynchronous
    def post(self):
        arguments = self.request.arguments
        device_ids = map(int, arguments.get('id'))
        devices = [session.query(Device).get(i) for i in device_ids]
        commands = {}
        for i in arguments:
            if i.startswith('input_'):
                name = i[len('input_'):]
                commands[name] = int(arguments.get(i)[0])

        t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        packet_id = randint(0, 32000)

        for device in devices:
            for input_name, value in commands.items():
                session.add(Measurement(
                    device=device,
                    ip_address=get_ip(self),
                    measurement_name=input_name,
                    measurement_value=value,
                    measurement_type='input',
                    timestamp=datetime.now(),
                    authority=True
                ))
        session.commit()

        all_connections = [
            connections[device.id]
            for device in devices if
            device.id in connections
        ]
        failures = [
            device.id for device in devices if
            device.id not in connections
        ]

        print("Got post, commands: %r" % commands)

        for connection in all_connections:
            waiting[(connection, packet_id)] = self
            connection.send_commands(commands, packet_id)

        if all_connections:
            yield gen.sleep(10)

        all_done = all_connections
        for connection in all_connections:
            val = waiting.pop((connection, packet_id), None)
            if val:
                failures.append(connection.device_id)
                all_done = False
        if all_done:
            print("Main thread abort, already responded")
            return
        self.end_post(failures)

    def end_post(self, failures):
        print("End, fail: %r" % failures)
        self.redirect(self.request.uri + ('&' + '&'.join('failure=%s'% f for f in failures)) if failures else '')

    def after_ws_response(self):
        if self not in waiting.items():
            self.end_post([])

unknown_connections = []
connections = {}
waiting = defaultdict(dict)


def get_ip(handler):
    return (
        handler.request.headers.get('X-Forwarded-For') or
        handler.request.remote_ip
    ) if hasattr(handler, 'request') else handler._stream.socket.getpeername()[0]


class DeviceLogicHandler(object):
    device_id = None

    def send_commands(self, commands, packet_id=0):
        msg = ("%d\n" % packet_id) + "\n".join("SET %s %d" % (name, value) for name, value in commands.items()) + "\n\n"
        print("Sending to %r, %r" % (self, msg))
        self.write_message(msg)

    def open(self):
        print("Open conn: {}".format(self))
        unknown_connections.append(self)
        timestamp = str(int(time.time()))
        self.write_message("10\nTIME " + timestamp+"\n\n") #+ "\nSET LED30 0\nSET LED32 1\nSET LED34 0")
        print ("SENDING TIMESTAMP: %s" % timestamp)

    def on_close(self):
        if not self.device_id:
            print("Close unknown conn: {}".format(self))
            unknown_connections.remove(self)
        else:
            print("Close conn: {}, {}".format(self.device_id, self))
            if connections.get(self.device_id) == self:
                del connections[self.device_id]

    def on_message(self, message):
        print("MSG: %r" % message)
        try:
            msg = json.loads(message)
            if not self.device_id:
                device = session.query(Device).filter(
                    Device.device_secret == msg['AUTH']
                ).first()
                if not device:
                    device = Device(
                        device_secret=msg['AUTH'],
                        device_name=msg['name'],
                        ip_address=get_ip(self),
                        last_seen=datetime.now()
                    )
                    session.add(device)
                    session.commit()
                self.device_id = device.id
                if not self.device_id:
                    import pudb
                    pu.db
                assert self.device_id
                if self.device_id in connections:
                    ex_connection = connections[self.device_id]
                    ex_connection.close()
                connections[self.device_id] = self
                unknown_connections.remove(self)

            device = session.query(Device).get(self.device_id)
            if not self.device_id or not device:
                import pudb
                pu.db
            assert device
            device.last_seen = datetime.now()
            device.ip_address = get_ip(self)
            # print("Message: {} msg: {}".format(self.device_id, msg))

            if 'status' in msg:
                packet_id = msg['packet_id']
                handler = waiting.pop((self, packet_id), None)
                if handler:
                    handler.after_ws_response()
            else:
                max_id = 0
                for measurement in msg['measurements']:
                    max_id = max(max_id, measurement['packet_id'])
                    device = device
                    ip_address = get_ip(self)
                    measurement_name = measurement['name']
                    measurement_value = measurement['value']
                    measurement_type = measurement['type']
                    timestamp = datetime.strptime(
                        measurement['time'],
                        '%Y-%m-%d %H:%M:%S'
                    )
                    if measurement_name == 'Boot':
                        for input_name in measurement['names']['input_names']:
                            session.add(Measurement(
                                device=device,
                                ip_address=ip_address,
                                measurement_name=input_name,
                                measurement_value=0,
                                measurement_type='input',
                                timestamp=timestamp
                            ))
                            if session:
                                ex = session.query(Measurement).filter(
                                    Measurement.device == device,
                                    Measurement.measurement_name == input_name,
                                    Measurement.authority
                                ).order_by(
                                    desc(Measurement.timestamp)
                                ).first()
                                if ex:
                                    connections[device.id].send_commands(
                                        {input_name: ex.measurement_value}
                                    )


                        for event_name in measurement['names']['event_names']:
                            session.add(Measurement(
                                device=device,
                                ip_address=ip_address,
                                measurement_name=event_name,
                                measurement_value=0,
                                measurement_type='event',
                                timestamp=timestamp
                            ))
                    else:
                        if session.query(Measurement).filter(
                            Measurement.device == device,
                            Measurement.measurement_name == measurement_name,
                            Measurement.timestamp == timestamp
                        ).count() == 0:
                            session.add(Measurement(
                                device=device,
                                ip_address=ip_address,
                                measurement_name=measurement_name,
                                measurement_value=measurement_value,
                                measurement_type=measurement_type,
                                timestamp=timestamp
                            ))
                self.write_message(json.dumps({'packet_id': max_id, 'status': 'ok'}))
            session.commit()
            return
        except TypeError as e:
            print("Error(%r), ignored: %r" % (e, message))
        except ValueError as e:
            print("Error(%r), ignored: %r" % (e, message))
        except KeyError as e:
            print("Missing needed values(%r), ignored: %r" % (e, message))
        session.rollback()


class DeviceHandler(websocket.WebSocketHandler, DeviceLogicHandler):
    pass


class TCPDeviceServer(TCPServer, DeviceLogicHandler):
    def write_message(self, data):
        self._stream.write(data.encode('ascii'))

    def _on_disconnect(self, *args, **kwargs):
        self.on_close()
        self.is_alive = False

    def handle_stream(self, stream, address):
        self.is_alive = True
        self._stream = stream
        self.open()
        self._stream.set_close_callback(self._on_disconnect)
        self._stream.read_until(b'\n', self._handle_read)

    def _handle_read(self, data):
        msg = (
            data.decode('ascii')
            .replace('\n', '')
            .replace('\r', '')
        )
        if msg:
            self.on_message(msg)
        self._stream.read_until(b'\n', self._handle_read)


application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/view_devices", ViewHandler),
    (r"/api", DeviceHandler),
])
tcp_application = TCPDeviceServer()

if __name__ == "__main__":
    if '-create' in sys.argv:
        print("Creating tables")
        Base.metadata.create_all(engine)
    elif '-dummy' in sys.argv:
        print("Creating dummy data")
        for i in range(3):
            device = Device(
                device_name='device %d' % i,
                ip_address='127.0.0.1',
                last_seen=datetime.now(),
                device_secret='secret %d' % i
            )
            session.add(device)
            session.add(Measurement(
                device=device,
                ip_address='127.0.0.1',
                measurement_name='Boot',
                measurement_type='event',
                measurement_value=1,
                timestamp=datetime.now() - timedelta(minutes=15*101)
            ))
            for name in ['temperature_in', 'temperature_out']:
                if i == 2 and name == 'temperature_out':
                    continue
                for m in range(100):
                    if m%100 in range(2*i*10, (2*i+1)*10):
                        continue
                    session.add(Measurement(
                        device=device,
                        ip_address='127.0.0.1',
                        measurement_name=name,
                        measurement_type='measurement',
                        measurement_value=(m+i) % 20 + randint(-10, 10),
                        timestamp=datetime.now() - timedelta(minutes=15*m)
                    ))
            for m in range(10):
                session.add(Measurement(
                    device=device,
                    ip_address='127.0.0.1',
                    measurement_name='Door sensor 1',
                    measurement_type='event',
                    measurement_value=1,
                    timestamp=datetime.now() - timedelta(minutes=15*m)
                ))
                session.add(Measurement(
                    device=device,
                    ip_address='127.0.0.1',
                    measurement_name='Door sensor 1',
                    measurement_type='event',
                    measurement_value=0,
                    timestamp=datetime.now() - timedelta(minutes=15*m) + timedelta(seconds=10)
                ))
            for name in ['Heating', 'Sauna', 'Alarm system', 'Unused']:
                session.add(Measurement(
                    device=device,
                    ip_address='127.0.0.1',
                    measurement_name=name,
                    measurement_type='input',
                    measurement_value=0,
                    timestamp=datetime.now() - timedelta(minutes=15*m) + timedelta(seconds=1)
                ))

        session.commit()

    else:
        print("Server start")
        application.listen(8888)
        tcp_application.listen(8889)
        try:
            tornado.ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            print("Shutdown")

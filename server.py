import json
import sys
from datetime import datetime, timedelta
from collections import OrderedDict
import tornado.ioloop
import tornado.web
from tornado import websocket
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    scoped_session,
    sessionmaker,
    relationship
)
Base = declarative_base()

engine = create_engine('postgresql+pg8000://localhost/cloudino')

session = scoped_session(sessionmaker(bind=engine))()


class Device(Base):
    __tablename__ = 'device'
    id = Column(Integer, primary_key=True)
    device_name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    device_secret = Column(String, nullable=False)

    measurements = relationship('Measurement', backref='device')
    inputs = relationship('Input', backref='device')


class Input(Base):
    __tablename__ = 'input'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('device.id'))
    name = Column(String, nullable=False)


class Measurement(Base):
    __tablename__ = 'measurement'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('device.id'))
    ip_address = Column(String, nullable=False)
    measurement_name = Column(String, nullable=False)
    measurement_value = Column(Integer, nullable=False)
    measurement_type = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("real_index.html", devices=session.query(Device).all())


class ViewHandler(tornado.web.RequestHandler):
    def get(self):
        device_ids = self.request.arguments.get('id', [])
        device_ids = list(set(map(int, device_ids)))
        inputs = {
            i[0] for i in
            (
                session.query(Input.name)
                .filter(
                    Input.device_id.in_(device_ids)
                )
                .order_by(Input.device_id, Input.id)
                .all()
            )
        }
        events = (
            session.query(Measurement)
            .filter(
                Measurement.measurement_type == 'event',
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
    measurement_name = '%s'
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
            inputs=inputs,
            events=events,
            measurements=measurements2,
            csvs=csvs
        )

unknown_connections = []
connections = {}


class DeviceHandler(websocket.WebSocketHandler):
    device_id = None

    def open(self):
        print "Open conn: {}".format(self)
        unknown_connections.append(self)

    def on_close(self):
        if not self.device_id:
            print "Close unknown conn: {}".format(self)
            unknown_connections.remove(self)
        else:
            print "Close conn: {}, {}".format(self.device_id, self)
            del connections[self.device_id]

    def on_message(self, message):
        msg = json.loads(message)
        if not self.device_id:
            device = session.query(Device).filter(
                Device.device_secret == msg['AUTH']
            ).first()
            if not device:
                device = Device(
                    device_secret=msg['AUTH'],
                    device_name=msg['name'],
                    ip_address='TODO',
                    last_seen=datetime.now()
                )
                session.add(device)
                session.flush()
            self.device_id = device.id
            if self.device_id in connections:
                ex_connection = connections[self.device_id]
                ex_connection.close()
                assert self.device_id not in connections
            connections[self.device_id] = self
            unknown_connections.remove(self)

        device = session.query(Device).get(self.device_id)
        device.last_seen = datetime.now()
        assert device
        print "Message: {} msg: {}".format(self.device_id, msg)
        max_id = 0
        for measurement in msg['measurements']:
            max_id = max(max_id, measurement['packet_id'])
            device = device
            ip_address = 'TODO'
            measurement_name = measurement['name']
            measurement_value = measurement['value']
            measurement_type = measurement['type']
            timestamp = datetime.strptime(
                measurement['time'],
                '%Y-%m-%d %H:%M:%S'
            )
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


application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/view_devices", ViewHandler),
    (r"/api", DeviceHandler),
])

if __name__ == "__main__":
    if '-create' in sys.argv:
        print "Creating tables"
        Base.metadata.create_all(engine)
    elif '-dummy' in sys.argv:
        print "Creating dummy data"
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
                measurement_name='Bootup',
                measurement_type='event',
                measurement_value='1',
                timestamp=datetime.now() - timedelta(minutes=15*101)
            ))
            for name in ['temperature_in', 'temperature_out']:
                if i == 2 and name == 'temperature_out':
                    continue
                for m in range(1000):
                    from random import randint
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
                    measurement_value='1',
                    timestamp=datetime.now() - timedelta(minutes=15*m)
                ))
                session.add(Measurement(
                    device=device,
                    ip_address='127.0.0.1',
                    measurement_name='Door sensor 1',
                    measurement_type='event',
                    measurement_value='0',
                    timestamp=datetime.now() - timedelta(minutes=15*m) + timedelta(seconds=10)
                ))
            for name in ['Heating', 'Sauna', 'Alarm system', 'Unused']:
                session.add(Input(
                    device=device,
                    name=name
                ))
        session.commit()

    else:
        print "Server start"
        application.listen(8888)
        try:
            tornado.ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            print "Shutdown"

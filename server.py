import sys

import tornado.ioloop
import tornado.web
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

engine = create_engine('postgres://localhost/cloudino')

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
        devices = session.query(Device).filter(Device.id.in_(device_ids)).all()
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
                Measurement.measurement_type=='event',
                Measurement.device_id.in_(device_ids)
            )
            .order_by(Measurement.timestamp)
        ).all()
        self.render("view_devices.html", inputs=inputs, events=events)


application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/view_devices", ViewHandler),
])

if __name__ == "__main__":
    if '-create' in sys.argv:
        print "Creating tables"
        Base.metadata.create_all(engine)
    elif '-dummy' in sys.argv:
        print "Creating dummy data"
        from datetime import datetime, timedelta
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
                for m in range(100):
                    session.add(Measurement(
                        device=device,
                        ip_address='127.0.0.1',
                        measurement_name=name,
                        measurement_type='measurement',
                        measurement_value=m,
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

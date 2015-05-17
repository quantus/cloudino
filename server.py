import sys

import tornado.ioloop
import tornado.web
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
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


class Measurement(Base):
    __tablename__ = 'measurement'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, nullable=False)
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
        self.render("view_devices.html")


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
            session.add(Device(
                device_name='device %d' % i,
                ip_address='127.0.0.1',
                last_seen=datetime.now(),
                device_secret='secret %d' % i
            ))
            for name in ['temperature_in', 'temperature_out']:
                for m in range(100):
                    session.add(Measurement(
                        device_id=i,
                        ip_address='127.0.0.1',
                        measurement_name=name,
                        measurement_type='measurement',
                        measurement_value=m,
                        timestamp=datetime.now() - timedelta(minutes=15*m)
                    ))

        session.commit()

    else:
        print "Server start"
        application.listen(8888)
        try:
            tornado.ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            print "Shutdown"

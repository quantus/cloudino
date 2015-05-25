# cloudino

This is kind of proof of concept project for IoT system without any security features.

# How to start
1. Install requirements
```$ pip3 install -r requirements.txt```
2. Add database URI to environment (SQLAlchemy format)
```$ export DATABASE_URI=postgresql+pypostgresql://localhost/cloudino```
3. Create database tables
```$ python3 server.py -create```
4. Add dummy data (Optional)
```$ python3 server.py -dummy```
5. Start server (server starts servering on port 8888)
```$ python3 server.py```

# Simulating devices

1. Start connection to the server 
```$ wsdump.py ws://localhost:8888/api```
2. Write valid message:
```{"AUTH": "secret", "name": "Cabin control 1", "measurements":[{"packet_id": 1, "type": "event", "time": "2015-01-01 11:11:12", "value": 1, "name": "Door sensor"},{"packet_id": 2, "type": "measurement", "time": "2015-01-01 11:11:14", "value": 12, "name": "Inside temp"},{"packet_id": 3, "type": "input", "time": "2015-01-01 11:11:15", "value": 0, "name": "Heating"}]}```

# License
Some of the arduino code is from https://github.com/brandenhall/Arduino-Websocket with unknown license. All python code is licenced under MIT license.

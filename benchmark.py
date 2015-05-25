import websocket
from datetime import datetime, timedelta

rounds = 100
time = datetime.now()

for i in range(rounds):
    t = (time + timedelta(minutes = 15*i)).strftime('%Y-%m-%d %H:%M:%S')
    ws = websocket.WebSocket()
    ws.connect("ws://localhost:8888/api")
    ws.send(
        '{"AUTH": "salainen", "name": "Cabin control 1", "measurements":[{"packet_id": 1, "type": "event", "time": "%s", "value": 1, "name": "Door sensor"},{"packet_id": 2, "type": "measurement", "time": "%s", "value": 123, "name": "Door temp"}]}'
        % (t, t)
    )
    ws.recv()
    ws.close()

elapsed = (datetime.now() - time).total_seconds() * 1000

print "%s loops took %s ms, %s ms per loop" % (rounds, elapsed, elapsed/rounds)

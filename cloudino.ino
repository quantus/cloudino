#include <SPI.h>
#include <GSM.h>
//#include <SC16IS750.h>
//#include <WiFly.h>

// Here we define a maximum framelength to 64 bytes. Default is 256.
#define MAX_FRAME_LENGTH 64

// Define how many callback functions you have. Default is 1.
#define CALLBACK_FUNCTIONS 1

#include "WebSocketClient.h"

GSMClient client;
GPRS gprs;
GSM gsmAccess;

// PIN Number
#define PINNUMBER "1234"

// APN data
#define GPRS_APN       "internet.saunalahti" // replace your GPRS APN
#define GPRS_LOGIN     ""    // replace with your GPRS login
#define GPRS_PASSWORD  "" // replace with your GPRS password

WebSocketClient webSocketClient;

void debugBlink(int blinkcount){
    int port = 34;
    pinMode(port, OUTPUT);
    digitalWrite(port, HIGH);
    delay(1000);
    for(int i=0;i<blinkcount;i++){
      digitalWrite(port, LOW);
      delay(300);
      digitalWrite(port, HIGH);
      delay(300);      
    }
    digitalWrite(port, LOW);
    delay(1000);
    pinMode(port, INPUT);
}

void setLed(int port){
  pinMode(port, OUTPUT);
  digitalWrite(port, HIGH);
  //pinMode(port, INPUT);
}

void startupLeds(){
    delay(500);
  // initialize serial communications and wait for port to open:
  for (int e=0; e<2; e++){
    for(int i=22; i<=34; i++){
      pinMode(i, OUTPUT);
      digitalWrite(i, HIGH);
      delay(100);
    }
    for(int i=22; i<=34; i++){
      digitalWrite(i, LOW);
      pinMode(i, INPUT);
      delay(100);
    }
  }
}

void setup() {  

  startupLeds();
  setLed(22); 
  debugBlink(1);
  
  for(int i=50; i<=53; i++) // listen events
    pinMode(i, INPUT);
    
  
  
  // connection state
  boolean notConnected = true;

  // After starting the modem with GSM.begin()
  // attach the shield to the GPRS network with thebe APN, login and password
  while(notConnected)
  {
    if((gsmAccess.begin(PINNUMBER)==GSM_READY) &&
      (gprs.attachGPRS(GPRS_APN, GPRS_LOGIN, GPRS_PASSWORD)==GPRS_READY))
      notConnected = false;
    else
    {
      debugBlink(3);
    }
  }
  setLed(24);
  //Serial.begin(9600);
  /*SC16IS750.begin();
  
  WiFly.setUart(&SC16IS750);
  
  WiFly.begin();
  
  // This is for an unsecured network
  // For a WPA1/2 network use auth 3, and in another command send 'set wlan phrase PASSWORD'
  // For a WEP network use auth 2, and in another command send 'set wlan key KEY'
  WiFly.sendCommand(F("set wlan auth 1"));
  WiFly.sendCommand(F("set wlan channel 0"));
  WiFly.sendCommand(F("set ip dhcp 1"));
  
  Serial.println(F("Joining WiFi network..."));
  

  // Here is where you set the network name to join
  if (!WiFly.sendCommand(F("join arduino_wifi"), "Associated!", 20000, false)) {    
    Serial.println(F("Association failed."));
    while (1) {
      // Hang on failure.
    }
  }
  
  if (!WiFly.waitForResponse("DHCP in", 10000)) {  
    Serial.println(F("DHCP failed."));
    while (1) {
      // Hang on failure.
    }
  }*/

  // This is how you get the local IP as an IPAddress object
  //Serial.println(WiFly.localIP());
  
  // This delay is needed to let the WiFly respond properly
  delay(1000);

  // Connect to the websocket server
  while(1){
  if(client.connect("173.255.197.142", 80)) {
    //Serial.println("Connected");
    break;
    client.println("GET /asede HTTP/1.1");
    client.println("Host: 04b5bc2b.ngrok.io");
    client.println("Connection: Close");
    client.println();
  } else {
    //Serial.println("Connection failed.");
    debugBlink(6);
  }
  }
  
  setLed(26);


  

  // Handshake with the server
  webSocketClient.path = "/api";
  webSocketClient.host = "04b5bc2b.ngrok.io";
  
  // JÄÄ TÄHÄN JUMIIN
  
  if (webSocketClient.handshake(client)) {
    //Serial.println("Handshake successful");
    //client.print("Handshake OK");
  } else {
    //Serial.println("Handshake failed.");
    //client.print("Handshake NOK");
    while(1) {
      // Hang on failure
      debugBlink(15);
    }  
  }
}

class event{
  event( int _packetid, int _type, String _time, int _value, int _pin, int _pin_status ){
    packetid = _packetid;
    type = _type;
    time = _time;
    value = _value;
    pin = _pin;
    pin_status = _pin_status;
  }
   int packetid;
   int type; // measurement / event
   String time;
   int value;
   int pin;
   int pin_status; // on / off

};

int pinStatus[100] = {0};

void loop() {
  String data;
  setLed(28);
  
  if (client.connected()) {
    
    webSocketClient.getData(data);

    if (data.length() > 0) {
      //Serial.print("Received data: ");
      //Serial.println(data);
    }
    setLed(30);
    
    // capture the value of analog 1, send it along
    //pinMode(1, INPUT);
    //data = String(analogRead(1));
    data = "{}";
    //webSocketClient.sendData(data);
    
    for(int i=50; i<=53; i++){
      int s = digitalRead(i);
      if (pinStatus[i] != s){
         if (s == HIGH){
           webSocketClient.sendData("{HIGH"+String(i)+"}");
         } else {
           webSocketClient.sendData("{LOW"+String(i)+"}");
         }
         pinStatus[i] = s;
      }
    }
    
    int analogValue = analogRead(A6);
    webSocketClient.sendData("{ANA"+String(analogValue)+"}");
    
    //webSocketClient.sendData("{}");
    setLed(32);
    
  } else {
    
    //Serial.println("Client disconnected.");3
    while (1) {
      // Hang on disconnect.
      debugBlink(10);
    }
  }
  
  
  // wait to fully let the client disconnect
  delay(3000);
}

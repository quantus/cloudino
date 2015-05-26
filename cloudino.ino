#include <SPI.h>
#include <GSM.h>
//#include <SC16IS750.h>
//#include <WiFly.h>

// Here we define a maximum framelength to 64 bytes. Default is 256.
#define MAX_FRAME_LENGTH 64

// Define how many callback functions you have. Default is 1.
#define CALLBACK_FUNCTIONS 1

#include "WebSocketClient.h"

template <typename T, size_t N>
inline size_t SizeOfArray( const T(&)[ N ] ){
  return N;
}

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

const int ledPins[] = {22,24,26,28,30,32,34};
const int debugLed = ledPins[0]; // the first one used as debug led
const int eventPins[] = {50,51,52,53};
const String eventName[] ={"AA","BB","CC","DD"};
const int measurementPins[] = {A6};
const String measurementName[] ={"XX"};

const int eventPinSize = SizeOfArray( eventPins );
const int measurementPinSize = SizeOfArray( measurementPins );
const int ledPinSize = SizeOfArray( ledPins );

boolean makeconnection(); 

void debugBlink(const int debugLed, const int errorcode){
    digitalWrite(debugLed, LOW);
    delay(1000);
    for(int i=0;i<errorcode;i++){
      digitalWrite(debugLed, HIGH);
      delay(300);
      digitalWrite(debugLed, LOW);
      delay(300);      
    }
    digitalWrite(debugLed, HIGH);
    delay(1000);
}


void startupLeds(){
   delay(500);

   for(int i=0; i<ledPinSize; i++){
     digitalWrite(ledPins[i], HIGH);
     delay(100);
   }
   for(int i=0; i<ledPinSize; i++){
     digitalWrite(ledPins[i], LOW);
     delay(100);
   }
}

void initializePINs(){
  for(int i=0; i<ledPinSize; i++){
      pinMode(ledPins[i], OUTPUT);
      digitalWrite(ledPins[i], LOW);
  }
  for(int i=0; i<eventPinSize; i++)
      pinMode(eventPins[i], INPUT);
  for(int i=0; i<measurementPinSize; i++)
      pinMode(measurementPins[i], INPUT);  
}

void initializeGSM(){ // issues? http://forum.arduino.cc/index.php?topic=270551.0
    // After starting the modem with GSM.begin() attach the shield to the GPRS network with thebe APN, login and password
  while(1){
    if((gsmAccess.begin(PINNUMBER)==GSM_READY) &&
      (gprs.attachGPRS(GPRS_APN, GPRS_LOGIN, GPRS_PASSWORD)==GPRS_READY)){
      break;
    } 
    debugBlink(debugLed,3);
  }
  delay(1000);
}


void setup() {  
  initializePINs();

  startupLeds();
  startupLeds();
  
  debugBlink(debugLed,1);

  initializeGSM();
  digitalWrite(ledPins[1], HIGH); //Serial.println("GSM successful");
  
  while(1){
    if (makeconnection())
      break; // connected
  }
}
boolean makeconnection(){
  webSocketClient.path = "/api";
  webSocketClient.host = "04b5bc2b.ngrok.io";

  digitalWrite(ledPins[2], LOW);
  digitalWrite(ledPins[3], LOW);
  digitalWrite(ledPins[4], LOW);
  digitalWrite(ledPins[5], LOW);

  
  if(client.connect("173.255.197.142", 80)) {
    digitalWrite(ledPins[2], HIGH); //Serial.println("Connection successful");
    if (webSocketClient.handshake(client)){
        digitalWrite(ledPins[3], HIGH); //Serial.println("Handshake successful");
        return true;
    } else {
        debugBlink(debugLed,15); //Serial.println("Handshake failed.");
        client.stop();
    }
  } else {
      debugBlink(debugLed,6);  //Serial.println("Connection failed.");
  }
  return false;

}

class record{
   public:
   record(){}
   record(bool _type, int _value, int _pin, String _time){
     type = _type;
     value = _value;
     pin = _pin;
     time = _time;
   }
   bool type; // measurement / event
   int value;
   int pin;
   String time;
};

record history[10];
int history_iterator = 0;
int pinStatus[100] = {0};

void isBufferFull(){
    if (10 <= history_iterator){
        history_iterator = 10;
        debugBlink(debugLed,10);    //Serial.println("Sorry. The buffer is full.");
    }
}

void fillBuffer(){
    for(int i=0; i<eventPinSize; i++){
        const int PIN = eventPins[i];
        int s = digitalRead(PIN);
  
        if (pinStatus[PIN] != s){
             record r = record(true, s, PIN, "0");            
             history[min(history_iterator++, 10)] = r;
             isBufferFull();
             pinStatus[PIN] = s;
        }
    }
    for(int i=0; i<measurementPinSize; i++){
        const int PIN = measurementPins[i];
        int analogValue = analogRead(PIN);
  
        if (pinStatus[PIN] != analogValue){
           record r = record(false, analogValue, PIN, "0");
           history[min(history_iterator++, 10)] = r;
           isBufferFull();
           pinStatus[PIN] = analogValue;
        }
    }
}

String pinToName(const int targetPIN){
    for(int i=0; i<eventPinSize; i++){
        const int PIN = eventPins[i];
        if (PIN == targetPIN){
           return eventName[i];
        }
    }
    for(int i=0; i<measurementPinSize; i++){
        const int PIN = measurementPins[i];
        if (PIN == targetPIN){
           return measurementName[i];
        }
    }
    return "";
}

void loop() {
  String data;
  
  fillBuffer();
  
  if (client.connected()) {
    
    webSocketClient.getData(data);

    if (data.length() > 0) {
      //Serial.println("Received data: " + data);
        digitalWrite(ledPins[4], HIGH);
    }
    
    if (history_iterator){
      data = String("{") + String("‘AUTH’:’SECRET_KEY2000005’,")
      + String("‘name:’JMT1 device’,")
      + String("‘measurements’: [");
      
      for (int i=0; i<history_iterator;  i++){
        const record R = history[i];
        String message = "{";
        if (R.type) message += "\"type\":\"event\"";
        else message += "\"type\":\"measurement\", ";
        message += "\"value\":\""+ String(R.value) +"\", ";
        message += "\"pin\":\""+ String(R.pin) +"\", ";
        message += "\"time\":\""+ R.time +"\", ";
        message += "\"name\":\""+ pinToName(R.pin) +"\", ";
        
        message += "}, ";
        data += message;
      }
      data += "]}";
      webSocketClient.sendData(data);
      history_iterator = 0;
     
      digitalWrite(ledPins[5], HIGH);
    }
  } else {
    debugBlink(debugLed,10);    //Serial.println("Connection disconnected.");
    while(1){
      if (makeconnection())
        break; // connected
      delay(3000);
    }
  }
  
  
  // wait to fully let the client disconnect
  // delay(3000); // wtf t:toni
}

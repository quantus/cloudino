#include <SPI.h>
#include <GSM.h>
//#include <SC16IS750.h>
//#include <WiFly.h>
#include "Time.h"  
#include <stdlib.h>
#include <avr/interrupt.h>  
#include <avr/io.h>

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

const String authtoken = "SECRET_KEY2000005";
const String devicename = "JMT1 device";
const int ledPins[] = {22,24,26,28,30,32,34};
const String ledName[] = {"LED22","LED24","LED26","LED28","LED30","LED32","LED34"};
const int debugLed = ledPins[0]; // the first one used as debug led
const int eventPins[] = {50,51,52,53};
const String eventName[] ={"Event50","Event51","Event52","Event53"};
const int measurementPins[] = {A6};
const String measurementName[] ={"MeasurementA6"};

const int eventPinSize = SizeOfArray( eventPins );
const int measurementPinSize = SizeOfArray( measurementPins );
const int ledPinSize = SizeOfArray( ledPins );
int pinStatus[100] = {0};

boolean makeconnection(); 

void debugBlink(const int debugLed, const unsigned long errorcode){
    for (int i=1; i<10; i++){
        digitalWrite(debugLed, LOW);
        delay(10+i*5);
        digitalWrite(debugLed, HIGH);
        delay(10+i*5);
    }
    delay(1000);
    for(unsigned long i=0;i<errorcode;i++){
      digitalWrite(debugLed, HIGH);
      delay(300);
      digitalWrite(debugLed, LOW);
      delay(300);      
    }
    digitalWrite(debugLed, HIGH);
}


void debugRequest(String message){
      webSocketClient.sendData("{\"message\":\""+message+"\"}");
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

/*
{
   "AUTH":"SECRET_KEY2000005",
   "name":"JMT1 device",
   "measurements":[
      {
         "type":"event",
         "packet_id":0,
         "value":0,
         "time":"",
         "name":"Boot",
         "names":{
            "input_names":[
               "LED22",
               "LED24",
               "LED26",
               "LED28",
               "LED30",
               "LED32",
               "LED34"
            ],
            "event_names":[
               "Event50",
               "Event51",
               "Event52",
               "Event53"
            ],
            "measurement_names":[
               "MeasurementA6"
            ]
         }
      }
   ]
}

*/
void bootEvent(){
      String data = String("{") + String("\"AUTH\":\""+authtoken+"\",")
      + String("\"name\":\""+devicename+"\",")
      + String("\"measurements\": [");
      
        data += "{";
        data += "\"type\":\"event\", ";
        data += "\"packet_id\":0, ";
        data += "\"value\":0, ";
        data += "\"time\":\"\", ";
        data += "\"name\":\"Boot\", ";
        
      data += String("\"names\": {");      
      data += "\"input_names\":[";
      for(int i=0; i<ledPinSize; i++){
        data += (i==0)?"\""+ledName[i]+"\"":(",\""+ledName[i]+"\"");
      }
      data += "],\"event_names\":[";
      for(int i=0; i<eventPinSize; i++){
        data += (i==0)?"\""+eventName[i]+"\"":(",\""+eventName[i]+"\"");
      }
      data += "],\"measurement_names\":[";
      for(int i=0; i<measurementPinSize; i++){
        data += (i==0)?"\""+measurementName[i]+"\"":(",\""+measurementName[i]+"\"");
      }
      data += "]}}]";
      webSocketClient.sendData(data);  
}

void initializeTimer(){
  //Setup Timer2 to fire every 1ms
  TCCR2B = 0x00;        //Disbale Timer2 while we set it up
  TCNT2  = 130;         //Reset Timer Count to 130 out of 255
  TIFR2  = 0x00;        //Timer2 INT Flag Reg: Clear Timer Overflow Flag
  TIMSK2 = 0x01;        //Timer2 INT Reg: Timer2 Overflow Interrupt Enable
  TCCR2A = 0x00;        //Timer2 Control Reg A: Normal port operation, Wave Gen Mode normal
  TCCR2B = 0x05;        //Timer2 Control Reg B: Timer Prescaler set to 128  
}


unsigned long int timerCounter = 0;

//Timer2 Overflow Interrupt Vector, called every 1ms
ISR(TIMER2_OVF_vect) {
  const unsigned long int seconds = 60*15;
  timerCounter++;
  if(timerCounter > 999*seconds){ // act every 15min
    for(int i=0; i<measurementPinSize; i++){
      pinStatus[measurementPins[i]]=-1; // trigger to send measurement events
    }
    timerCounter = 0;
  }
  TCNT2 = 130;           //Reset Timer to 130 out of 255
  TIFR2 = 0x00;          //Timer2 INT Flag Reg: Clear Timer Overflow Flag
};  

void setup() {  
  initializePINs();

  startupLeds();
  startupLeds();
  
  debugBlink(debugLed,0);

  unsigned long pctime;
  const unsigned long DEFAULT_TIME = 1357041600; //1357041600; // Jan 1 2013
  setTime(DEFAULT_TIME);

  initializeGSM();
  digitalWrite(ledPins[1], HIGH); //Serial.println("GSM successful");
  
  while(1){
    if (makeconnection())
      break; // connected
  }
  bootEvent();
  initializeTimer();
}
boolean makeconnection(){
  webSocketClient.path = "/api";
  webSocketClient.host = "892c05e9.ngrok.io"; // "04b5bc2b.ngrok.io";

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
      debugBlink(debugLed,2);  //Serial.println("Connection failed.");
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
 
const int history_size = 100;
record history[history_size];
int history_iterator = 0;

void isBufferFull(){
    if (history_size-1 <= history_iterator){
        history_iterator = history_size-1;
        debugBlink(debugLed,10);    //Serial.println("Sorry. The buffer is full.");
    }
}

void fillBuffer(){ 
     //time_t t = now();

     
     const String Y = String(year());
     const String M = String(month());
     const String D = String(day());
     const String h = String(hour());
     const String m = String(minute());
     const String s = String(second());
     
     String time = Y;
     time += "-" + ((M.length()==2)?M:"0"+M);
     time += "-" + ((D.length()==2)?D:"0"+D);
     time += " " + ((h.length()==2)?h:"0"+h);
     time += ":" + ((m.length()==2)?m:"0"+m);
     time += ":" + ((s.length()==2)?s:"0"+s);
  
    for(int i=0; i<eventPinSize; i++){
        const int PIN = eventPins[i];
        int s = digitalRead(PIN);
  
        if (pinStatus[PIN] != s){
             record r = record(true, s, PIN, time);            
             history[history_iterator++] = r;
             isBufferFull();
             pinStatus[PIN] = s;
        }
    }
    for(int i=0; i<measurementPinSize; i++){
        const int PIN = measurementPins[i];
        int analogValue = analogRead(PIN);
  
        if (pinStatus[PIN] != analogValue){
           record r = record(false, analogValue, PIN, time);
           history[history_iterator++] = r;
           isBufferFull();
           pinStatus[PIN] = analogValue;
        }
    }
}

int nameToPin(const char *name_){
    String name = (String)(name_);
    for(int i=0; i<eventPinSize; i++){
        const String pin_name = eventNames[i];
        if (name == pin_name){
           return eventPins[i];
        }
    }
    for(int i=0; i<measurementPinSize; i++){
        const String pin_name = measurementNames[i];
        if (name == pin_name){
           return measurementPins[i];
        }
    }
    for(int i=0; i<ledPinSize; i++){
        const int pin_name = ledNames[i];
        if (name == pin_name){
           return ledPins[i];
        }
    }
    return 0;
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
    for(int i=0; i<ledPinSize; i++){
        const int PIN = ledPins[i];
        if (PIN == targetPIN){
           return ledName[i];
        }
    }
    return "";
}
/*
{  "names":[
     "input_names":{"A","b","c"},
     "event_names":{"A","b","c"},
     "measurement_names":{"A","b","c"}
   ]
}
*/


void loop() {
  String data;
  
  fillBuffer();
  debugBlink(34,0);
  
  if (client.connected()) {
    
    webSocketClient.getData(data);

    if (data.length() > 0) {
      //Serial.println("Received data: " + data);
        digitalWrite(ledPins[4], HIGH);

        const char *lines = data.c_str();
        // lue ekalta riviltä lähetyksen id\n
        int packet_id = 1337, offset = 0;
        if (sscanf(lines, "%d%n", &packet_id, &offset)==1){
            lines += offset+1;
         }


        unsigned long pctime=0;
        int pin=0, mode=0;
        for (int i=0; i<100; i++){
/*
          if (sscanf(lines, "SET %d %d%n", &pin, &mode, &offset)==2){ // PIN pitäs olla pin_name
            lines += offset+1;
            digitalWrite(pin, mode);
            //printf("read: command=SET, x=%d, y=%d; offset = %5d, val=%d\n", x,y, offset, val);
            continue;
          }
*/
          char pin_word[1000]; // TODO: buffer overflow
          if (sscanf(lines, "SET %s %d%n", &pin_word, &mode, &offset)==2){ // PIN pitäs olla pin_name
            lines += offset+1;
            const int pin = nameToPin(pin_word); //atoi(pin_word); // TEEE
            digitalWrite(pin, mode);
            //printf("read: command=SET, x=%d, y=%d; offset = %5d, val=%d\n", x,y, offset, val);
            continue;
          }
          if (sscanf(lines, "TIME %lu%n", &pctime, &offset)==1){
            lines += offset+1;
            // debugRequest("read: command=TIME, x=" + String(pctime));
            setTime(pctime);
            continue;
          }
    
          break;
        }
        //int packet_id = 123;
        String ack = "{\"status\":\"ok\",\"packet_id\":"+String(packet_id)+"}";
        webSocketClient.sendData(data);
        // kuittaus {"status":"ok","packet_id":123}

        
          

        
    }

    static int packet_counter = 0;

    // debugBlink(34,history_iterator); // wtf
    
    if (history_iterator){
      data = String("{") + String("\"AUTH\":\""+authtoken+"\",")
      + String("\"name\":\""+devicename+"\",")
      + String("\"measurements\": [");
      
      for (int i=0; i<history_iterator;  i++){
        const record R = history[i];
        String message = i==0?"{":",{";
        if (R.type) message += "\"type\":\"event\", ";
        else message += "\"type\":\"measurement\", ";
        message += "\"packet_id\":"+ String(packet_counter++) +", ";
        message += "\"value\":"+ String(R.value) +", ";
        message += "\"pin\":"+ String(R.pin) +", ";
        message += "\"time\":\""+ R.time +"\", ";
        message += "\"name\":\""+ pinToName(R.pin) +"\" ";
        
        message += "}";
//        debugRequest(message);
        
        data += message;
      }
      
      data += "]}";
      webSocketClient.sendData(data);
      history_iterator = 0;
     
      digitalWrite(ledPins[5], HIGH);
    }
  } else {
    // debugBlink(debugLed,10);    //Serial.println("Connection disconnected.");
    if (makeconnection())
      bootEvent();
  }
  
  
  // wait to fully let the client disconnect
  // delay(3000); // wtf t:toni
}

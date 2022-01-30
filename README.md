# Interface with Home Connect appliances in Python

This is a very, very beta interface for Bosch-Siemens Home Connect
devices through their local network connection.  It has some tools
to find the TLS PSK (Pre-shared Key) that is used to allow local
access, and a Python script that can construct the proper Websocket
interface to subscribe to events.

*WARNING: This is not ready for prime time!*


## Finding the PSK

You'll need to find the PSK for your devices with a rooted
Android phone and the `find-psk.frida` script for Frida.

```
frida --no-pause -f com.bshg.homeconnect.android.release -U -l find-psk.frida
```

It should print a message like:

```
psk callback hint 'HCCOM_Local_App'
psk 32 0x6ee63fb2f0
           0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F  0123456789ABCDEF
00000000  0e c8 1f d8 c6 49 fa d8 bc e7 fd 34 33 54 13 d4  .....I.....43T..
00000010  73 f9 2e 01 fc d8 26 80 49 89 4c 19 d7 2e cd cb  s.....&.I.L.....
```

Which gives you the 32-byte PSK value.

## SSL logging

The Frida script will also dump all of the SSL traffic so that you can
see different endpoints and things.  Not much is documented yet.

Note that the TX from the phone on the websocket is "masked" with an
repeating 4-byte XOR that is sent in the first part of each messages.
The script could be augmented to decode those as well.
The replies from the device are not masked so they can be read in the clear.

## hcpy

The `hcpy` tool can contact your device, and if the PSK is correct, it will
register for notification of events.

```
RX: {'sID': 2354590730, 'msgID': 3734589701, 'resource': '/ei/initialValues', 'version': 2, 'action': 'POST', 'data': [{'edMsgID': 3182729968}]}
TX: {"sID":2354590730,"msgID":3734589701,"resource":"/ei/initialValues","version":2,"action":"RESPONSE","data":[{"deviceType":"Application","deviceName":"py-hca","deviceID":"1234"}]}
TX: {"sID":2354590730,"msgID":3182729968,"resource":"/ci/services","version":1,"action":"GET"}
TX: {"sID":2354590730,"msgID":3182729969,"resource":"/iz/info","version":1,"action":"GET"}
TX: {"sID":2354590730,"msgID":3182729970,"resource":"/ei/deviceReady","version":2,"action":"NOTIFY"}
RX: {'sID': 2354590730, 'msgID': 3182729968, 'resource': '/ci/services', 'version': 1, 'action': 'RESPONSE', 'data': [{'service': 'ci', 'version': 3}, {'service': 'ei', 'version': 2}, {'service': 'iz', 'version': 1}, {'service': 'ni', 'version': 1}, {'service': 'ro', 'version': 1}]}
RX: {'sID': 2354590730, 'msgID': 3182729969, 'resource': '/iz/info', 'version': 1, 'action': 'RESPONSE', 'data': [{'deviceID': '....', 'eNumber': 'SX65EX56CN/11', 'brand': 'SIEMENS', 'vib': 'SX65EX56CN', 'mac': '....', 'haVersion': '1.4', 'swVersion': '3.2.10.20200911163726', 'hwVersion': '2.0.0.2', 'deviceType': 'Dishwasher', 'deviceInfo': '', 'customerIndex': '11', 'serialNumber': '....', 'fdString': '0201', 'shipSki': '....'}]}
```


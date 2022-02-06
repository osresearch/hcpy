# Create a websocket that wraps a connection to a
# Bosh-Siemens Home Connect device
import socket
import ssl
import sslpsk
import websocket
import sys
import json
import re
import time
import io
from base64 import urlsafe_b64decode as base64url
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Hash import HMAC, SHA256
from Crypto.Random import get_random_bytes

# Convience to compute an HMAC on a message
def hmac(key,msg):
	mac = HMAC.new(key, msg=msg, digestmod=SHA256).digest()
	return mac

def now():
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

# Monkey patch for sslpsk in pip using the old _sslobj
def _sslobj(sock):
    if (3, 5) <= sys.version_info <= (3, 7):
        return sock._sslobj._sslobj
    else:
        return sock._sslobj
sslpsk.sslpsk._sslobj = _sslobj


class HCSocket:
	def __init__(self, host, psk64, iv64=None):
		self.host = host
		self.psk = base64url(psk64 + '===')
		self.debug = False

		if iv64:
			# an HTTP self-encrypted socket
			self.http = True
			self.iv = base64url(iv64 + '===')
			self.enckey = hmac(self.psk, b'ENC')
			self.mackey = hmac(self.psk, b'MAC')
			self.port = 80
			self.uri = "ws://" + host + ":80/homeconnect"
		else:
			self.http = False
			self.port = 443
			self.uri = "wss://" + host + ":443/homeconnect"

		# don't connect automatically so that debug etc can be set
		#self.reconnect()

	# restore the encryption state for a fresh connection
	# this is only used by the HTTP connection
	def reset(self):
		if not self.http:
			return
		self.last_rx_hmac = bytes(16)
		self.last_tx_hmac = bytes(16)

		self.aes_encrypt = AES.new(self.enckey, AES.MODE_CBC, self.iv)
		self.aes_decrypt = AES.new(self.enckey, AES.MODE_CBC, self.iv)

	# hmac an inbound or outbound message, chaining the last hmac too
	def hmac_msg(self, direction, enc_msg):
		hmac_msg = self.iv + direction + enc_msg
		return hmac(self.mackey, hmac_msg)[0:16]

	def decrypt(self,buf):
		if len(buf) < 32:
			print("Short message?", buf.hex(), file=sys.stderr)
			return None
		if len(buf) % 16 != 0:
			print("Unaligned message? probably bad", buf.hex(), file=sys.stderr)

		# split the message into the encrypted message and the first 16-bytes of the HMAC
		enc_msg = buf[0:-16]
		their_hmac = buf[-16:]

		# compute the expected hmac on the encrypted message
		our_hmac = self.hmac_msg(b'\x43' + self.last_rx_hmac, enc_msg)

		if their_hmac != our_hmac:
			print("HMAC failure", their_hmac.hex(), our_hmac.hex(), file=sys.stderr)
			return None

		self.last_rx_hmac = their_hmac

		# decrypt the message with CBC, so the last message block is mixed in
		msg = self.aes_decrypt.decrypt(enc_msg)

		# check for padding and trim it off the end
		pad_len = msg[-1]
		if len(msg) < pad_len:
			print("padding error?", msg.hex())
			return None

		return msg[0:-pad_len]

	def encrypt(self, clear_msg):
		# convert the UTF-8 string into a byte array
		clear_msg = bytes(clear_msg, 'utf-8')

		# pad the buffer, adding an extra block if necessary
		pad_len = 16 - (len(clear_msg) % 16)
		if pad_len == 1:
			pad_len += 16
		pad = b'\x00' + get_random_bytes(pad_len-2) + bytearray([pad_len])

		clear_msg = clear_msg + pad

		# encrypt the padded message with CBC, so there is chained
		# state from the last cipher block sent
		enc_msg = self.aes_encrypt.encrypt(clear_msg)

		# compute the hmac of the encrypted message, chaining the
		# hmac of the previous message plus direction 'E'
		self.last_tx_hmac = self.hmac_msg(b'\x45' + self.last_tx_hmac, enc_msg)

		# append the new hmac to the message
		return enc_msg + self.last_tx_hmac

	def reconnect(self):
		self.reset()
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.connect((self.host,self.port))

		if not self.http:
			sock = sslpsk.wrap_socket(
				sock,
				ssl_version = ssl.PROTOCOL_TLSv1_2,
				ciphers = 'ECDHE-PSK-CHACHA20-POLY1305',
				psk = self.psk,
			)

		print(now(), "CON:", self.uri)
		self.ws = websocket.WebSocket()
		self.ws.connect(self.uri,
			socket = sock,
			origin = "",
		)

	def send(self, msg):
		buf = json.dumps(msg, separators=(',', ':') )
		# swap " for '
		buf = re.sub("'", '"', buf)
		if self.debug:
			print(now(), "TX:", buf)
		if self.http:
			self.ws.send_binary(self.encrypt(buf))
		else:
			self.ws.send(buf)

	def recv(self):
		buf = self.ws.recv()
		if buf is None or buf == "":
			return None

		if self.http:
			buf = self.decrypt(buf)
		if buf is None:
			return None

		if self.debug:
			print(now(), "RX:", buf)
		return buf

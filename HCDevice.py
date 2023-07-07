#!/usr/bin/env python3
# Parse messages from a Home Connect websocket (HCSocket)
# and keep the connection alive
#
# Possible resources to fetch from the devices:
#
# /ro/values
# /ro/descriptionChange
# /ro/allMandatoryValues
# /ro/allDescriptionChanges
# /ro/activeProgram
# /ro/selectedProgram
#
# /ei/initialValues
# /ei/deviceReady
#
# /ci/services
# /ci/registeredDevices
# /ci/pairableDevices
# /ci/delregistration
# /ci/networkDetails
# /ci/networkDetails2
# /ci/wifiNetworks
# /ci/wifiSetting
# /ci/wifiSetting2
# /ci/tzInfo
# /ci/authentication
# /ci/register
# /ci/deregister
#
# /ce/serverDeviceType
# /ce/serverCredential
# /ce/clientCredential
# /ce/hubInformation
# /ce/hubConnected
# /ce/status
#
# /ni/config
#
# /iz/services

import sys
import json
import re
import time
import io
import traceback
from datetime import datetime
from base64 import urlsafe_b64encode as base64url_encode
from Crypto.Random import get_random_bytes


def now():
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

class HCDevice:
	def __init__(self, ws, features, name):
		self.ws = ws
		self.features = features
		self.session_id = None
		self.tx_msg_id = None
		self.device_name = "hcpy"
		self.device_id = "0badcafe"
		self.debug = False
		self.name = name

	def parse_values(self, values):
		if not self.features:
			return values

		result = {}

		for msg in values:
			uid = str(msg["uid"])
			value = msg["value"]
			value_str = str(value)

			name = uid
			status = None

			if uid in self.features:
				status = self.features[uid]

			if status:
				name = status["name"]
				if "values" in status \
				and value_str in status["values"]:
					value = status["values"][value_str]

			# trim everything off the name except the last part
			name = re.sub(r'^.*\.', '', name)
			result[name] = value

		return result

	# Test the feature of an appliance agains a data object
	def test_feature(self, data):
		if 'uid' not in data:
			raise Exception("{self.name}. Unable to configure appliance. UID is required.")

		if isinstance(data['uid'], int) == False:
			raise Exception("{self.name}. Unable to configure appliance. UID must be an integer.")

		if 'value' not in data:
			raise Exception("{self.name}. Unable to configure appliance. Value is required.")

		# Check if the uid is present for this appliance
		uid = str(data['uid'])
		if uid not in self.features:
			raise Exception(f"{self.name}. Unable to configure appliance. UID {uid} is not valid.")

		feature = self.features[uid]

		# check the access level of the feature
		print(now(), self.name, f"Processing feature {feature['name']} with uid {uid}")
		if 'access' not in feature:
			raise Exception(f"{self.name}. Unable to configure appliance. Feature {feature['name']} with uid {uid} does not have access.")

		access = feature['access'].lower()
		if access != 'readwrite' and access != 'writeonly':
			raise Exception(f"{self.name}. Unable to configure appliance. Feature {feature['name']} with uid {uid} has got access {feature['access']}.")

		# check if selected list with values is allowed
		if 'values' in feature:
			if isinstance(data['value'], int) == False:
				raise Exception(f"Unable to configure appliance. The value {data['value']} must be an integer. Allowed values are {feature['values']}.")
			value = str(data['value']) # values are strings in the feature list, but always seem to be an integer. An integer must be provided
			if value not in feature['values']:
				raise Exception(f"{self.name}. Unable to configure appliance. Value {data['value']} is not a valid value. Allowed values are {feature['values']}.")

		if 'min' in feature:
			min = int(feature['min'])
			max = int(feature['min'])
			if isinstance(data['value'], int) == False or data['value'] < min or data['value'] > max:
				raise Exception(f"{self.name}. Unable to configure appliance. Value {data['value']} is not a valid value. The value must be an integer in the range {min} and {max}.")

		return True

	def recv(self):
		try:
			buf = self.ws.recv()
			if buf is None:
				return None
		except Exception as e:
			print(self.name, "receive error", e, traceback.format_exc())
			return None

		try:
			return self.handle_message(buf)
		except Exception as e:
			print(self.name, "error handling msg", e, buf, traceback.format_exc())
			return None

	# reply to a POST or GET message with new data
	def reply(self, msg, reply):
		self.ws.send({
			'sID': msg["sID"],
			'msgID': msg["msgID"], # same one they sent to us
			'resource': msg["resource"],
			'version': msg["version"],
			'action': 'RESPONSE',
			'data': [reply],
		})

	# send a message to the device
	def get(self, resource, version=1, action="GET", data=None):
		msg = {
			"sID": self.session_id,
			"msgID": self.tx_msg_id,
			"resource": resource,
			"version": version,
			"action": action,
		}

		if data is not None:
			if action == "POST":
				if self.test_feature(data) != True:
					return
				msg["data"] = [data]
			else:
				msg["data"] = [data]

		try:
			self.ws.send(msg)
		except Exception as e:
			print(self.name, "Failed to send", e, msg, traceback.format_exc())
		self.tx_msg_id += 1

	def handle_message(self, buf):
		msg = json.loads(buf)
		if self.debug:
			print(now(), self.name, "RX:", msg)
		sys.stdout.flush()

		resource = msg["resource"]
		action = msg["action"]

		values = {}

		if "code" in msg:
			print(now(), self.name, "ERROR", msg["code"])
			values = {
				"error": msg["code"],
				"resource": msg.get("resource", ''),
			}
		elif action == "POST":
			if resource == "/ei/initialValues":
				# this is the first message they send to us and
				# establishes our session plus message ids
				self.session_id = msg["sID"]
				self.tx_msg_id = msg["data"][0]["edMsgID"]

				self.reply(msg, {
					"deviceType": "Application",
					"deviceName": self.device_name,
					"deviceID": self.device_id,
				})

				# ask the device which services it supports
				self.get("/ci/services")

				# the clothes washer wants this, the token doesn't matter,
				# although they do not handle padding characters
				# they send a response, not sure how to interpet it
				token = base64url_encode(get_random_bytes(32)).decode('UTF-8')
				token = re.sub(r'=', '', token)
				self.get("/ci/authentication", version=2, data={"nonce": token})

				self.get("/ci/info", version=2)  # clothes washer
				self.get("/iz/info")  # dish washer
				#self.get("/ci/tzInfo", version=2)
				self.get("/ni/info")
				#self.get("/ni/config", data={"interfaceID": 0})
				self.get("/ei/deviceReady", version=2, action="NOTIFY")
				self.get("/ro/allDescriptionChanges")
				self.get("/ro/allDescriptionChanges")
				self.get("/ro/allMandatoryValues")
				#self.get("/ro/values")
			else:
				print(now(), self.name, "Unknown resource", resource, file=sys.stderr)

		elif action == "RESPONSE" or action == "NOTIFY":
			if resource == "/iz/info" or resource == "/ci/info":
				# we could validate that this matches our machine
				pass

			elif resource == "/ro/descriptionChange" \
			or resource == "/ro/allDescriptionChanges":
				# we asked for these but don't know have to parse yet
				pass

			elif resource == "/ni/info":
				# we're already talking, so maybe we don't care?
				pass

			elif resource == "/ro/allMandatoryValues" \
			or resource == "/ro/values":
				if 'data' in msg:
					values = self.parse_values(msg["data"])
				else:
					print(now(), self.name, f"received {msg}")
			elif resource == "/ci/registeredDevices":
				# we don't care
				pass

			elif resource == "/ci/services":
				self.services = {}
				for service in msg["data"]:
					self.services[service["service"]] = {
						"version": service["version"],
					}
				#print(self.name, now(), "services", self.services)

				# we should figure out which ones to query now
#				if "iz" in self.services:
#					self.get("/iz/info", version=self.services["iz"]["version"])
#				if "ni" in self.services:
#					self.get("/ni/info", version=self.services["ni"]["version"])
#				if "ei" in self.services:
#					self.get("/ei/deviceReady", version=self.services["ei"]["version"], action="NOTIFY")

				#self.get("/if/info")

		else:
			print(now(), self.name, "Unknown", msg)

		# return whatever we've parsed out of it
		return values

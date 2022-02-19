#!/usr/bin/env python3
# Convert the featuremap and devicedescription XML files into a single JSON
# this collapses the XML entities and duplicates some things, but makes for
# easier parsing later
#
# Program groups are ignored for now
#

import sys
import json
import xml.etree.ElementTree as ET

#####################
#
# Parse the description file and collapse everything into a single
# list of UIDs
#

def parse_xml_list(codes, entries, enums):
	for el in entries:
		# not sure how to parse refCID and refDID
		uid = int(el.attrib["uid"], 16)

		if not uid in codes:
			print("UID", uid, " not known!", file=sys.stderr)

		data = codes[uid];
		if "uid" in codes:
			print("UID", uid, " used twice?", data, file=sys.stderr)

		for key in el.attrib:
			data[key] = el.attrib[key]

		# clean up later
		#del data["uid"]

		if "enumerationType" in el.attrib:
			del data["enumerationType"]
			enum_id = int(el.attrib["enumerationType"], 16)
			data["values"] = enums[enum_id]["values"]

		#codes[uid] = data

def parse_machine_description(entries):
	description = {}

	for el in entries:
		prefix, has_namespace, tag = el.tag.partition('}')
		if tag != "pairableDeviceTypes":
			description[tag] = el.text

	return description


def xml2json(features_xml,description_xml):
	# the feature file has features, errors, and enums
	# for now the ordering is hardcoded
	featuremapping = ET.fromstring(features_xml) #.getroot()
	description = ET.fromstring(description_xml) #.getroot()

	#####################
	#
	# Parse the feature file
	#

	features = {}
	errors = {}
	enums = {}

	# Features are all possible UIDs
	for child in featuremapping[1]: #.iter('feature'):
		uid = int(child.attrib["refUID"], 16)
		name = child.text
		features[uid] = {
			"name": name,
		}

	# Errors
	for child in featuremapping[2]: 
		uid = int(child.attrib["refEID"], 16)
		name = child.text
		errors[uid] = name

	# Enums
	for child in featuremapping[3]: 
		uid = int(child.attrib["refENID"], 16)
		enum_name = child.attrib["enumKey"]
		values = {}
		for v in child:
			value = int(v.attrib["refValue"])
			name = v.text
			values[value] = name
		enums[uid] = {
			"name": enum_name,
			"values": values,
		}


	for i in range(4,8):
		parse_xml_list(features, description[i], enums)

	# remove the duplicate uid field
	for uid in features:
		if "uid" in features[uid]:
			del features[uid]["uid"]

	return {
		"description": parse_machine_description(description[3]),
		"features": features,
	}

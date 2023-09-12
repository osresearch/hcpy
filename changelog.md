# Changelog

All notable changes to this project will be documented in this file.

## 2023.9.12.1
### Added
- Ability to configure MQTT clientname

### Changed
- There was a default set of values being published. Now the device publishes what is present as access read, or readWrite in the `config.json`

### Fixed
- MQTT was not always published to the correct topic

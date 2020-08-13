# scheduler-component
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
## Introduction
This is a custom component for Home Assistant, that is used for adding the `scheduler` domain.
It works nicely together with the [Lovelace scheduler card](https://github.com/nielsfaber/scheduler-card).

A scheduler entity defines an action at a certain time, for example 'turn on my lamp at 21:00 every day'.
Any entity in HA can be used for making a scheduler entity, together with any service that is available in HA.

## Installation
Run this command from your HA config folder to automatically download and move the files:
```
curl https://raw.githubusercontent.com/nielsfaber/scheduler-component/master/install.sh | sh
```

Otherwise clone or download the source code as a zip file and add/merge the `custom_components/` folder with its contents in your configuration directory.


## Configuration
Add to `configuration.yaml`:

```yaml
scheduler:
```

## Services

### scheduler.turn_on
Enables a scheduler entity.
When an entity is enabled, the internal timer will be running and upon expiring the service call will be executed.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ------------|
| entity_id | entity id | **required** | `scheduler.schedule_123456` | Entity ID of the scheduler entity


### scheduler.turn_off
Disables a scheduler entity.
The internal timer will be disabled, so no services are executed at the programmed time.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ------------|
| entity_id | entity id | **required** | `scheduler.schedule_123456` | Entity ID of the scheduler entity


### scheduler.add
Add a new scheduler entity.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| time | string | **required** | "12:00" | Entity ID of the scheduler entity, e.g.
| days | list | none | `- 0`<br />`- 1` | List with specific days for which you want the timer to trigger (0=Sunday, 6=Saturday)
| entity | entity | **required** | `light.my_lamp` | Entity ID of the device that you want to trigger
| service | string | **required** | `turn_on` | Service that must be executed when the timer expires
| service_data | map | none | `brightness:100` | Extra arguments to pass to the service call


### scheduler.edit
Update the configuration of a scheduler entity.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| entity_id | entity id | **required** | `scheduler.schedule_123456` | Entity ID of the scheduler entity
| time | string | none | "12:00" | Entity ID of the scheduler entity, e.g.
| days | list | none | `- 0`<br />`- 1` | List with specific days for which you want the timer to trigger (0=Sunday, 6=Saturday)

*Note that not all properties are editable at this point. This is a work-in-progress.*


### scheduler.remove
Remove a scheduler entity.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| entity_id | entity id | **required** | `scheduler.schedule_123456` | Entity ID of the scheduler entity


### scheduler.test
Test the action (entity + service combination) that is configured.
This will have the same behaviour as it will have when the timer expires.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| entity_id | entity id | **required** | `scheduler.schedule_123456` | Entity ID of the scheduler entity

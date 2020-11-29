# scheduler-component
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
## Introduction
This is a custom component for Home Assistant, that is used for controlling your existing devices based on time.
It works nicely together with the [Lovelace scheduler card](https://github.com/nielsfaber/scheduler-card).

A scheduler entity defines an action at a certain time, for example 'turn on my lamp at 21:00 every day'.
Any entity in HA can be used for making a scheduler entity, together with any service that is available in HA.

## Installation

### Step 1: Download files

#### Option 1: Via HACS

Make sure you have HACS installed. If you don't, run `curl -sfSL https://hacs.xyz/install | bash -` in HA.  
Choose Integrations under HACS. Then hit the plus button, search for "scheduler", choose it, and hit install in HACS.

#### Option 2: Manual
Clone this repository or download the source code as a zip file and add/merge the `custom_components/` folder with its contents in your configuration directory.


### Step 2: Restart HA
In order for the newly added integration to be loaded, HA needs to be restarted.

### Step 3: Add integration
In HA, go to Configuration > Integrations.
In the bottom right corner, click on the big button with a '+'.

If the component is properly installed, you should be able to find the 'Scheduler integration' in the list.

Select it, and the scheduler integration is ready for use.

### Step 4: Add the scheduler-card
Follow instructions on [Lovelace scheduler card](https://github.com/nielsfaber/scheduler-card) to setup the card that allows you to configure scheduler entities.

## Scheduler entities
Entities that are part of the scheduler integrations will have entity id following according to pattern `switch.schedule_<token>`, where `<token>` is a randomly generated 6 digit code.

You can treat these entities in the same way as other `switch` entities in HA, meaning that you could place them in any Lovelace card for quick access. 

### States
A scheduler entity can have the following states:

| State | Description |
|------|-------------|
| `off` | Schedule is disabled.  A disabled schedule will not keep track of time, and will not execute any actions. |
| `waiting` | Schedule has internal timer running and is waiting for the timer to expire. The attribute `next trigger` provides the moment of expiration  |
| `triggered` | Timer is finished and the action is executed. Entity will wait for 1 minute and then reset the timer. |
| `initializing` `unknown` | Something went wrong, the schedule is not running. |


### Services
Since schedules follow the `switch` platform, you can use the `switch.turn_on` and `switch.turn_off` services to enable and disable schedules.

#### scheduler.add
Add a new scheduler entity.

| Name | Type | Default | Description |
|------|------|---------|-------------|
| actions | list | **required** | One or more [Actions](#action) |
| entries | list | **required** | One or more  [Entries](#entry) |

##### Action
An action defines the service calls to be executed.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- |-------------|
| service | string | **required** | `turn_on` | Service that must be executed when the timer expires
| entity | entity | **required** | `light.my_lamp` | Entity ID of the device that you want to trigger
| service_data | map | none | `brightness:100` | Extra arguments to pass to the service call


##### Entry
An entry defined the time on which to trigger one or more actions.

Fixed time entry:
| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| time | time | **required** | "12:00" | Time on which the actions should be triggered
| days | list | none | `- 1`<br />`- 2` | List with specific days for which you want the timer to trigger (1=Monday, 7=Sunday)
| actions | list | **required** | - 0 | List of action indexes to be executed on the specified time

Variable with sun time entry:
| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| event | string | "sunrise" or "sunset" | "sunrise" | Reference time point
| offset | time | none | "-01:00" | Time difference w.r.t. the reference time point
| days | list | none | `- 1`<br />`- 2` | List with specific days for which you want the timer to trigger (1=Monday, 7=Sunday) 
| actions | list | **required** | - 0 | List of actions to be executed on the specified time

#### scheduler.edit
Update the configuration of a scheduler entity.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| entity_id | entity id | **required** | `switch.schedule_123456` | Entity ID of the scheduler entity
| actions | list | **required** | See action | One or more [Actions](#action) |
| entries | list | **required** | See entry | One or more  [Entries](#entry) |

*Note that not all properties are editable at this point. This is a work-in-progress.*


#### scheduler.remove
Remove a scheduler entity.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| entity_id | entity id | **required** | `switch.schedule_123456` | Entity ID of the scheduler entity


#### scheduler.test
Test the action (entity + service combination) that is configured.
This will have the same behaviour as it will have when the timer expires.

| Name | Type | Default | Example | Description |
|------|------|---------|-------- | ----------- |
| entity_id | entity id | **required** | `switch.schedule_123456` | Entity ID of the scheduler entity
| entry | int | Optional | 0 | Index of the entry to be executed

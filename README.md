# scheduler-component
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
## Introduction
This is a custom component for Home Assistant, that is used for controlling your existing devices based on time.
It works nicely together with the [Lovelace scheduler card](https://github.com/nielsfaber/scheduler-card).

A scheduler entity defines an action at a certain time, for example 'turn on my lamp at 21:00 every day'.
Any entity in HA can be used for making a scheduler entity, together with any service that is available in HA.

## Installation

### Step 1: Download files

#### Option 1: Via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nielsfaber&repository=scheduler-card&category=integration)

Make sure you have HACS installed. If you don't, run `wget -O - https://get.hacs.xyz | bash -` in HA.  
Choose Integrations under HACS. Click the '+' button on the bottom of the page, search for "scheduler component", choose it, and click install in HACS.

#### Option 2: Manual
Clone this repository or download the source code as a zip file and add/merge the `custom_components/` folder with its contents in your configuration directory.


### Step 2: Restart HA
In order for the newly added integration to be loaded, HA needs to be restarted.

### Step 3: Add integration to HA (<--- this is a step that a lot of people forget)
In HA, go to Configuration > Integrations.
In the bottom right corner, click on the big button with a '+'.

If the component is properly installed, you should be able to find 'Scheduler' in the list. You might need to clear you browser cache for the integration to show up.


Select it, and the scheduler integration is ready for use.

### Step 4: Add the scheduler-card
Follow instructions on [Lovelace scheduler card](https://github.com/nielsfaber/scheduler-card) to setup the card that allows you to configure scheduler entities.


## Updating
1. Update the files:
   - Using HACS:
   In the HACS panel, there should be an notification when a new version is available. Follow the instructions within HACS to update the installation files.
   - Manually:
   Download the [latest release](https://github.com/nielsfaber/scheduler-component/releases/latest) as a zip file and extract it into the custom_components folder in your HA installation, overwriting the previous installation.
2. Restart HA to load the changes.

**To see which version is installed:**
In HA, go to Configuration -> Integrations. In the Scheduler integration card, you should see a link with '1 device', click it. In the table click the 'Scheduler' device, and you should see the Device info. The 'firmware version' represents the installed version number.

## Uninstalling

1. Remove scheduler from HA:
In HA go to Configuration -> Integrations. Find the card for scheduler integration, click the button with the 3 dots, and click 'Delete'.
2. Remove the files:
- When installed with HACS:
In the HACS panel go to integrations and look for Scheduler component. Click the button with the 3 dots and click 'Uninstall'.
- When installed manually:
In the custom_components directory, remove the 'scheduler' folder.
3. Restart HA to make all traces of the component disappear.

## Backup
The configuration of your schedules is stored in the `.storage` folder in the HA configuration directory, in a file called `scheduler.storage`.

If you create a snapshot through HA supervisor, this file should automatically be backed up. Else, make sure to include this file in your backup.

The entities in HA are created from the `scheduler.storage` file upon (re)starting HA.

## Scheduler entities
Entities that are part of the scheduler integrations will have entity id following according to pattern `switch.schedule_<token>`, where `<token>` is a randomly generated 6 digit code.

You can treat these entities in the same way as other `switch` entities in HA, meaning that you could place them in any Lovelace card for quick access. 

### States
A scheduler entity can have the following states:

| State       | Description                                                                                                                                |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `off`       | Schedule is disabled.  A disabled schedule will not keep track of time, and will not execute any actions.                                  |
| `on`        | Schedule has internal timer running and is waiting for the timer to expire. The attribute `next_trigger` provides the moment of expiration |
| `triggered` | Timer is finished and the action is executed. Entity will wait for 1 minute and then reset the timer.                                      |
| `unknown`   | Something went wrong, the schedule is not running.                                                                                         |


### Services
Since schedules follow the `switch` platform, you can use the `switch.turn_on` and `switch.turn_off` services to enable and disable schedules.

In addition, the following services are available.
Note that this component is meant to be used together with the [Lovelace scheduler card](https://github.com/nielsfaber/scheduler-card), which handles some of the data validation. 


#### scheduler.add
Add a new scheduler entity.

| field         | Type   | Optional/required | Description                                                           | Remarks                                                                                                                                                                                                                                               |
| ------------- | ------ | ----------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `weekdays`    | list   | optional          | Days (of the week) on which the schedule should be executed           | Valid values are: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`, `daily`, `workday` `weekend`.<br>Defaults to `daily`.                                                                                                                              |
| `start_date`  | date   | optional          | Starting date at which the schedule should trigger                    | Valid format is `yyyy-mm-dd`.                                                                                                                                                                                                                         |
| `end_date`    | date   | optional          | Final date for which the schedule should trigger                      | Valid format is `yyyy-mm-dd`.<br>If `end_date` is in the past, schedule will not trigger again.                                                                                                                                                       |
| `timeslots`   | list   | required          | List of times/time intervals with the actions that should be executed | See [Timeslot](#timeslot) for more info.                                                                                                                                                                                                              |
| `repeat_type` | string | optional          | Control repeat behaviour after triggering.                            | Valid values are: <ul><li>`repeat`: (default value) schedule will loop after triggering</li><li>`single`: schedule will delete itself after triggering</li><li>`pause`: schedule will turn off after triggering, can be reset by turning on</li></ul> |
| `name`        | string | optional          | Friendly name for the schedule entity.                                | The name will also be used for the entity_id of the schedule.<br> Default value is `Schedule #abcdef                     ` where `abcdef`=random generated sequence.                                                                                  |


#### scheduler.edit
Update the configuration of an existing scheduler entity.
Overwrites the old value. 

The service parameters are the same as for `scheduler.add`, except that the `entity_id` needs to be provided of the schedule which needs to be modified.

Note that only the parameters that should be changed have to be provided, if a parameter is not provided, the previous value will be kept.
                                                                                                                                                 
#### scheduler.remove
Remove a scheduler entity.

| field       | Type   | Optional/required | Description                       | Remarks                       |
| ----------- | ------ | ----------------- | --------------------------------- | ----------------------------- |
| `entity_id` | string | required          | Entity ID of the scheduler entity | e.g. `switch.schedule_123456` |

                                                                     
#### scheduler.copy
Duplicate a scheduler entity.

| field       | Type   | Optional/required | Description                                    | Remarks                                                                                                                                                              |
| ----------- | ------ | ----------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `entity_id` | string | required          | Entity ID of the existing scheduler entity     | e.g. `switch.schedule_123456`                                                                                                                                        |
| `name`      | string | optional          | Friendly name for the created schedule entity. | The name will also be used for the entity_id of the schedule.<br> Default value is `Schedule #abcdef                     ` where `abcdef`=random generated sequence. |



#### scheduler.run_action
Manually trigger a schedule.

| field             | Type    | Optional/required | Description                                                      | Remarks                                                                                                                                                                                                                                                                                                                     |
| ----------------- | ------- | ----------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `entity_id`       | string  | required          | Entity ID of the scheduler entity                                | e.g. `switch.schedule_123456`                                                                                                                                                                                                                                                                                               |
| `time`            | string  | optional          | Time for which to trigger the schedule.                          | If a schedule only has a single timeslot, this timeslot will always be triggered.<br>For schedules with a multiple timeslots: <ul><li>If no time is provided: the schedule overlapping the current time (now) is triggered.</li><li>If time is provided: the schedule overlapping the provided time is triggered.</li></ul> |
| `skip_conditions` | boolean | optional          | Whether the conditions of the schedule should be skipped or not. |                                                                                                                                                                                                                                                                                                                             |

### Data format

#### Timeslot
A timeslot defines the timepoints on which a schedule is triggered, together with the actions that need to be executed. Optionally also conditions can be specified that need to be validated before the actions may be fired.

| Name               | Type    | Optional/required | Description                                                                           | Remarks                                                                                                                                                               |
| ------------------ | ------- | ----------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `start`            | string  | required          | Time (in 24 hours format) on which the schedule should trigger                        | Should be in the range 00:00-23:59.<br>Each timeslot should have a unique value.<br> Input may also be relative to sun: e.g. `sunrise+01:00` or `sunset-00:00`.       |
| `stop`             | string  | optional          | Time (in 24 hours format) on which the timeslot ends                                  | Only required when defining timeslots.<br> Should be in the range 00:01-00:00 (start of next day).<br>The `stop` time must be at least one minute after `start` time. |
| `conditions`       | list    | optional          | Conditions that should be validated before the action(s) may be executed              | See [Condition](#condition) for more info.                                                                                                                            |
| `condition_type`   | string  | optional          | Logic to apply when validating multiple conditions                                    | Valid values are:<ul><li>`and`: All conditions must be met</li><li>`or`: One or more of the conditions must be met</li></ul>                                          |
| `track_conditions` | boolean | optional          | Watch condition entities for changes, repeat the actions once conditions become valid |                                                                                                                                                                       |
| `actions`          | list    | required          | Actions to execute when the `start` time is reached.                                  | See [Action](#action) for more info.                                                                                                                                  |

**Note**:

To guarantee compatibility with the scheduler-card, the following conditions need to be met:
1. A schedule must exist of either: 
  <ul>
    <li>A single timeslot with only <code>start</code> time</li>
    <li>A list timeslots which ALL have <code>start</code>  and <code>stop</code> time, which are non overlapping and are not relative to sun.</li>
  </ul>

2. Conditions must be the same for all timeslots.


3. Actions list may only consist of a single service/service_data combination (multiple actions may only have different entity_id).
  

### Condition

A condition is used for defining a rule that needs to be validated, before the scheduled action(s) may be executed.
Conditions are currently limited to checking the state of entities.

| Name         | Type   | Optional/required | Description                           | Remarks                                                                                                                                                                                                                                                                                                          |
| ------------ | ------ | ----------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `entity_id`  | string | required          | Entity to which the condition applies | e.g. `binary_sensor.my_window`                                                                                                                                                                                                                                                                                   |
| `value`      | string | required          | Value to compare the entity state to  | e.g. `on`                                                                                                                                                                                                                                                                                                        |
| `match_type` | string | required          | Logic to apply for the comparison     | Valid values are: <ul><li>`is`: entity state must match `value`</li><li>`not`: entity state must not match `value`</li><li>`below`: entity state must be below `value` (applicable to numerical values only)</li><li>`above`: entity state must be above `value` (applicable to numerical values only)</li></ul> |

### Action

An action is a combination of a HA service with entity_id. 
See Developer Tools -> Services in HA for available actions and info on valid parameters.

| Name           | Type   | Optional/required | Description                                        | Remarks                   |
| -------------- | ------ | ----------------- | -------------------------------------------------- | ------------------------- |
| `entity_id`    | string | required          | Entity to which the action needs to be executed    | e.g.: `light.my_lamp`     |
| `service`      | string | required          | HA service that needs to be executed on the entity | e.g.: `light.turn_on`     |
| `service_data` | dict   | optional          | Extra parameters to use in the service call.       | e.g.: `{brightness: 200}` |

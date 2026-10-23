# EER mapping

The eight entities map to eight tables. Composite attributes are flattened into columns. Relationship foreign keys are added on the many side; many-to-many relationships and multivalued bounding boxes need their own tables. The resulting schema has 13 tables.

| EER entity | Table | Primary key | Relationship foreign keys |
| --- | --- | --- | --- |
| ACCIDENT_PARTY | `accident_party` | `national_id` | — |
| VEHICLE | `vehicle` | `vehicle_id` | `national_id` registers/owns the vehicle |
| ACCIDENT_CASE | `accident_case` | `case_id` | `reviewed_by_expert_id` is optional |
| DASHCAM_VIDEO | `dashcam_video` | `video_id` | `case_id`, `national_id` identify its case and uploader |
| DETECTED_EVENT | `detected_event` | `event_id` | `video_id` produces the event |
| DETECTED_VEHICLE | `detected_vehicle` | `detected_vehicle_id` | `vehicle_id` optionally matches a registered vehicle |
| AUTHORIZED_EXPERT | `authorized_expert` | `expert_id` | — |
| FINAL_REPORT | `final_report` | `report_id` | unique `case_id`; optional `approved_by_expert_id` |

| EER relationship or attribute | Table | Key and values |
| --- | --- | --- |
| Participates | `participates` | PK (`national_id`, `case_id`) |
| Involves | `involves` | PK (`case_id`, `vehicle_id`) |
| INVOLVEMENT | `involvement` | PK (`event_id`, `vehicle_role`); `detected_vehicle_id`, `track_id`; event/detected-vehicle pair is unique |
| Bounding boxes [1..*] | `bounding_box` | PK (`event_id`, `vehicle_role`, `bounding_box`); parent FK to involvement |
| Receives | `receives` | PK (`report_id`, `national_id`) |

`vehicle.manufacturer`, `model`, `year` and `color` are the components of `car_details`. Plate letters and numbers are separate fields. All other entity attributes retain the EER names.

Each case has at most two participants and two linked vehicles. A linked vehicle belongs to a participant, with one vehicle per party in a case. Each party can upload one video per case. An event can involve at most two detected vehicles. A case has at most one final report, with up to two recipients who participate in that case.

Draft cases are allowed while the user enters the required data. Submission requires a participant, a linked vehicle and a video. Both parties and both vehicles are required when the case enters review. PostgreSQL also checks minimum bounding boxes and report recipients through deferred constraints.

In a rear-end case only `party_a_position` is stored; the second party's car is always the opposite position.

This mapping prepares storage for detection and reports. It does not implement automatic analysis, report creation screens or expert approval workflows.

## Supporting tables (not in the EER)

The website needs a few tables that are not part of the EER. They only hold technical data for running the site.

| Table | Why the website needs it |
| --- | --- |
| `participation_progress` | Each party's position (A or B), the step they reached, whether they submitted, and their picture choices in the accident description |
| `case_invitation` | The private invitation link sent to the second party: its token, expiry and whether it was used |
| `password_reset_link` | Password reset links: token, expiry and whether they were used |
| `login_attempt` | Wrong login attempts, to stop login for 15 minutes after 5 tries |
| `video_processing` | The uploaded file's original name and its privacy/analysis processing status |

The tables are created by `schema.py` when the website starts. `database/postgresql.sql` and `database/sqlite.sql` show the same statements.

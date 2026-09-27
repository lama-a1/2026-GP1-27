<p align="center">
  <img src="siyaq-logo.png" alt="Siyaq Logo" width="300">
</p>

# Siyaq

## About Siyaq

**Siyaq** is a graduation project developed to support the analysis of minor traffic accidents using dashcam footage.

The system is a **web-based AI decision-support system** that uses computer vision to analyze dashcam videos, detect and track relevant vehicles, examine vehicle movements, and identify traffic events and predefined violations.

Based on the extracted evidence, Siyaq applies **rule-based reasoning derived from relevant Saudi traffic regulations** to generate a suggested fault percentage of **0%, 25%, 50%, 75%, or 100%**.

The generated result is supported by relevant evidence and reasoning and is reviewed by an **authorized expert**, who can approve or modify the suggested fault percentage before the final result is issued.

---

## Key Features

- **Dashcam Video Analysis** – Analyzes submitted dashcam footage to extract relevant information about the accident.

- **Vehicle Detection and Tracking** – Detects relevant vehicles and follows their movement across video frames.

- **Traffic Event Analysis** – Examines vehicle movements and identifies relevant traffic events and predefined violations.

- **Rule-Based Fault Estimation** – Applies predefined rules derived from relevant Saudi traffic regulations to generate a suggested fault percentage.

- **Explainable Results** – Presents supporting evidence and reasoning alongside the suggested fault percentage.

- **Expert Review and Approval** – Allows an authorized expert to review the case, modify the suggested fault percentage when necessary, and provide final approval.

- **One or Two Video Support** – Requires one dashcam video from the first accident party and allows an optional second video from the other party. Each video is analyzed independently.

- **Accident Case Management** – Allows accident parties to submit cases and review their final approved results.

- **Privacy Protection** – Requires explicit consent for dashcam footage processing and applies privacy safeguards to accident reports.

---

## Supported Accident Scenarios

Siyaq currently focuses on two types of minor traffic accidents:

- **Rear-End Collisions**
- **Lane-Change Accidents**

The current project scope is limited to **no-injury, property-damage-only accidents** recorded during **daytime and clear weather conditions**.

---

## System Overview

**Dashcam Video(s) → Video Processing → Vehicle Detection & Tracking → Movement & Event Analysis → Rule-Based Fault Estimation → Expert Review → Final Result**

The first accident party submits one required dashcam video, while the second party may optionally submit an additional video.

Each submitted video is analyzed independently using computer vision techniques. The system extracts relevant evidence about vehicle movements and traffic events. The extracted evidence is then evaluated using predefined rules based on relevant Saudi traffic regulations.

Siyaq generates a suggested fault percentage together with supporting evidence and reasoning. An authorized expert reviews the generated analysis and makes the final decision.

---

## Fault Percentage

Siyaq uses the following proportional fault levels:

**0% · 25% · 50% · 75% · 100%**

The generated percentage is a **suggested assessment** intended to support the authorized expert. Siyaq does not independently issue legally binding fault decisions.

---

## Technologies

| Component | Technology |
|---|---|
| AI / Computer Vision | Python |
| Video Processing | OpenCV |
| Vehicle Detection | YOLO |
| Fault Assessment | Rule-Based Reasoning |
| Backend | Web Development Framework |
| Database | SQL Database |
| Messaging | Twilio Programmable Messaging API |
| Development Environment | Visual Studio Code |
| Project Management | Jira |
| Version Control | Git & GitHub |

---

## Siyaq Team

Developed by Information Technology students at  
**King Saud University – College of Computer and Information Sciences**

### Team Members

- Raneem Alroaini
- Jana Almengash
- Lama Almubarak
- Waad Alghamdi

### Supervisor

**Dr. Hessah Alsaaran**

---

## Project Status

Siyaq is currently under development as part of the **IT 496 Graduation Project**.

The project is being developed incrementally using the **Scrum framework**.

---

<div align="center">

### Siyaq | سياق

**AI-Assisted Traffic Accident Analysis**

</div>

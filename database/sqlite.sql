-- Siyaq EER schema

CREATE TABLE IF NOT EXISTS accident_party (
            national_id TEXT PRIMARY KEY NOT NULL, full_name TEXT NOT NULL, date_of_birth TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            notify_status_change INTEGER NOT NULL DEFAULT 1 CHECK (notify_status_change IN (0,1)),
            notify_final_result INTEGER NOT NULL DEFAULT 1 CHECK (notify_final_result IN (0,1)));

CREATE TABLE IF NOT EXISTS authorized_expert (
            expert_id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS vehicle (
            vehicle_id INTEGER PRIMARY KEY, plate_number TEXT NOT NULL CHECK (length(plate_number) BETWEEN 1 AND 4),
            plate_letters TEXT NOT NULL CHECK (length(plate_letters) BETWEEN 1 AND 8),
            manufacturer TEXT NOT NULL, model TEXT NOT NULL, year INTEGER NOT NULL, color TEXT NOT NULL,
            national_id TEXT NOT NULL REFERENCES accident_party(national_id));

CREATE TABLE IF NOT EXISTS accident_case (
            case_id TEXT PRIMARY KEY NOT NULL, party_b_email TEXT, accident_type TEXT NOT NULL
                CHECK (accident_type IN ('REAR_END','LANE_CHANGE')),
            party_a_position TEXT CHECK (party_a_position IN ('FRONT','REAR')),
            accident_date TEXT NOT NULL, accident_time TEXT NOT NULL, location TEXT NOT NULL,
            party_a_description TEXT, party_b_description TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by_expert_id BIGINT REFERENCES authorized_expert(expert_id));

CREATE TABLE IF NOT EXISTS participates (
            national_id TEXT NOT NULL REFERENCES accident_party(national_id),
            case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            PRIMARY KEY (national_id,case_id));

CREATE TABLE IF NOT EXISTS involves (
            case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            vehicle_id BIGINT NOT NULL REFERENCES vehicle(vehicle_id),
            PRIMARY KEY (case_id,vehicle_id));

CREATE TABLE IF NOT EXISTS dashcam_video (
            video_id INTEGER PRIMARY KEY, storage_path TEXT NOT NULL UNIQUE,
            camera_type TEXT NOT NULL CHECK (camera_type IN ('front','rear')),
            uploaded_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP), case_id TEXT NOT NULL,
            national_id TEXT NOT NULL, UNIQUE (case_id,national_id),
            FOREIGN KEY (national_id,case_id) REFERENCES participates(national_id,case_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS detected_event (
            event_id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, event_value TEXT, frame_path TEXT,
            start_time REAL NOT NULL, end_time REAL NOT NULL CHECK (end_time >= start_time),
            video_id BIGINT NOT NULL REFERENCES dashcam_video(video_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS detected_vehicle (
            detected_vehicle_id INTEGER PRIMARY KEY, vehicle_id BIGINT REFERENCES vehicle(vehicle_id));

CREATE TABLE IF NOT EXISTS involvement (
            event_id BIGINT NOT NULL REFERENCES detected_event(event_id) ON DELETE CASCADE,
            detected_vehicle_id BIGINT NOT NULL REFERENCES detected_vehicle(detected_vehicle_id),
            vehicle_role TEXT NOT NULL, track_id TEXT NOT NULL,
            PRIMARY KEY (event_id,vehicle_role), UNIQUE (event_id,detected_vehicle_id));

CREATE TABLE IF NOT EXISTS bounding_box (
            event_id BIGINT NOT NULL, vehicle_role TEXT NOT NULL, bounding_box TEXT NOT NULL,
            PRIMARY KEY (event_id,vehicle_role,bounding_box),
            FOREIGN KEY (event_id,vehicle_role) REFERENCES involvement(event_id,vehicle_role) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS final_report (
            report_id INTEGER PRIMARY KEY, outcome TEXT, suggested_party_a_fault REAL,
            suggested_party_b_fault REAL, party_a_fault REAL, party_b_fault REAL,
            undetermined_code TEXT, applied_rule TEXT, expert_notes TEXT, final_description TEXT,
            approved_at TEXT, case_id TEXT NOT NULL UNIQUE REFERENCES accident_case(case_id) ON DELETE CASCADE,
            approved_by_expert_id BIGINT REFERENCES authorized_expert(expert_id));

CREATE TABLE IF NOT EXISTS receives (
            report_id BIGINT NOT NULL REFERENCES final_report(report_id) ON DELETE CASCADE,
            national_id TEXT NOT NULL REFERENCES accident_party(national_id),
            PRIMARY KEY (report_id,national_id));

CREATE TABLE IF NOT EXISTS participation_progress (
            national_id TEXT NOT NULL, case_id TEXT NOT NULL,
            position TEXT NOT NULL CHECK (position IN ('A','B')),
            progress INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
            description_meta TEXT, joined_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            PRIMARY KEY (national_id,case_id), UNIQUE (case_id,position),
            FOREIGN KEY (national_id,case_id) REFERENCES participates(national_id,case_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS case_invitation (
            invitation_id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, recipient_email TEXT NOT NULL, expires_at TEXT NOT NULL,
            claimed_by TEXT REFERENCES accident_party(national_id), revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP));

CREATE TABLE IF NOT EXISTS password_reset_link (
            link_id INTEGER PRIMARY KEY, national_id TEXT NOT NULL REFERENCES accident_party(national_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL, used_at TEXT);

CREATE TABLE IF NOT EXISTS login_attempt (
            key TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, locked_until REAL);

CREATE TABLE IF NOT EXISTS video_processing (
            video_id BIGINT PRIMARY KEY REFERENCES dashcam_video(video_id) ON DELETE CASCADE,
            original_name TEXT NOT NULL, processed_path TEXT,
            privacy_status TEXT NOT NULL DEFAULT 'pending', note TEXT,
            job_status TEXT NOT NULL DEFAULT 'queued', job_details TEXT,
            updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP));

CREATE INDEX IF NOT EXISTS participates_case_idx ON participates(case_id);

CREATE INDEX IF NOT EXISTS vehicle_owner_idx ON vehicle(national_id);

CREATE INDEX IF NOT EXISTS dashcam_case_idx ON dashcam_video(case_id);

CREATE TRIGGER IF NOT EXISTS participates_max_two BEFORE INSERT ON participates
                WHEN (SELECT count(*) FROM participates WHERE case_id=NEW.case_id) >= 2 BEGIN SELECT RAISE(ABORT,'A case can have at most two accident parties'); END;

CREATE TRIGGER IF NOT EXISTS participates_max_two_update BEFORE UPDATE ON participates
                WHEN OLD.case_id<>NEW.case_id AND (SELECT count(*) FROM participates WHERE case_id=NEW.case_id) >= 2
                BEGIN SELECT RAISE(ABORT,'A case can have at most two accident parties'); END;

CREATE TRIGGER IF NOT EXISTS involves_max_two BEFORE INSERT ON involves
                WHEN (SELECT count(*) FROM involves WHERE case_id=NEW.case_id) >= 2 BEGIN SELECT RAISE(ABORT,'A case can involve at most two vehicles'); END;

CREATE TRIGGER IF NOT EXISTS involves_max_two_update BEFORE UPDATE ON involves
                WHEN OLD.case_id<>NEW.case_id AND (SELECT count(*) FROM involves WHERE case_id=NEW.case_id) >= 2
                BEGIN SELECT RAISE(ABORT,'A case can involve at most two vehicles'); END;

CREATE TRIGGER IF NOT EXISTS involvement_max_two BEFORE INSERT ON involvement
                WHEN (SELECT count(*) FROM involvement WHERE event_id=NEW.event_id) >= 2 BEGIN SELECT RAISE(ABORT,'An event can involve at most two detected vehicles'); END;

CREATE TRIGGER IF NOT EXISTS involvement_max_two_update BEFORE UPDATE ON involvement
                WHEN OLD.event_id<>NEW.event_id AND (SELECT count(*) FROM involvement WHERE event_id=NEW.event_id) >= 2
                BEGIN SELECT RAISE(ABORT,'An event can involve at most two detected vehicles'); END;

CREATE TRIGGER IF NOT EXISTS receives_max_two BEFORE INSERT ON receives
                WHEN (SELECT count(*) FROM receives WHERE report_id=NEW.report_id) >= 2 BEGIN SELECT RAISE(ABORT,'A report can have at most two recipients'); END;

CREATE TRIGGER IF NOT EXISTS receives_max_two_update BEFORE UPDATE ON receives
                WHEN OLD.report_id<>NEW.report_id AND (SELECT count(*) FROM receives WHERE report_id=NEW.report_id) >= 2
                BEGIN SELECT RAISE(ABORT,'A report can have at most two recipients'); END;

CREATE TRIGGER IF NOT EXISTS involves_owner BEFORE INSERT ON involves
                WHEN NOT EXISTS (
            SELECT 1 FROM vehicle v JOIN participates p ON p.national_id=v.national_id
            WHERE v.vehicle_id=NEW.vehicle_id AND p.case_id=NEW.case_id) BEGIN SELECT RAISE(ABORT,'Vehicle owner must participate in this case'); END;

CREATE TRIGGER IF NOT EXISTS involves_owner_update BEFORE UPDATE ON involves
                WHEN NOT EXISTS (
            SELECT 1 FROM vehicle v JOIN participates p ON p.national_id=v.national_id
            WHERE v.vehicle_id=NEW.vehicle_id AND p.case_id=NEW.case_id) BEGIN SELECT RAISE(ABORT,'Vehicle owner must participate in this case'); END;

CREATE TRIGGER IF NOT EXISTS involves_one_per_owner BEFORE INSERT ON involves
                WHEN EXISTS (
            SELECT 1 FROM involves i JOIN vehicle a ON a.vehicle_id=i.vehicle_id
            JOIN vehicle b ON b.vehicle_id=NEW.vehicle_id
            WHERE i.case_id=NEW.case_id AND a.national_id=b.national_id AND i.vehicle_id<>NEW.vehicle_id) BEGIN SELECT RAISE(ABORT,'Each party has one vehicle in a case'); END;

CREATE TRIGGER IF NOT EXISTS involves_one_per_owner_update BEFORE UPDATE ON involves
                WHEN EXISTS (
            SELECT 1 FROM involves i JOIN vehicle a ON a.vehicle_id=i.vehicle_id
            JOIN vehicle b ON b.vehicle_id=NEW.vehicle_id
            WHERE i.case_id=NEW.case_id AND a.national_id=b.national_id AND i.vehicle_id<>NEW.vehicle_id) BEGIN SELECT RAISE(ABORT,'Each party has one vehicle in a case'); END;

CREATE TRIGGER IF NOT EXISTS receives_participant BEFORE INSERT ON receives
                WHEN NOT EXISTS (
            SELECT 1 FROM final_report f JOIN participates p ON p.case_id=f.case_id
            WHERE f.report_id=NEW.report_id AND p.national_id=NEW.national_id) BEGIN SELECT RAISE(ABORT,'Report recipient must participate in the case'); END;

CREATE TRIGGER IF NOT EXISTS receives_participant_update BEFORE UPDATE ON receives
                WHEN NOT EXISTS (
            SELECT 1 FROM final_report f JOIN participates p ON p.case_id=f.case_id
            WHERE f.report_id=NEW.report_id AND p.national_id=NEW.national_id) BEGIN SELECT RAISE(ABORT,'Report recipient must participate in the case'); END;

CREATE TRIGGER IF NOT EXISTS case_submission_check BEFORE UPDATE OF status ON accident_case
            WHEN NEW.status IN ('pending','in_progress','completed','approved') AND (
        (SELECT count(*) FROM participates WHERE case_id=NEW.case_id)<1 OR
        (SELECT count(*) FROM involves WHERE case_id=NEW.case_id)<1 OR
        (SELECT count(*) FROM dashcam_video WHERE case_id=NEW.case_id)<1 OR
        (NEW.status IN ('in_progress','completed','approved') AND (
            (SELECT count(*) FROM participates WHERE case_id=NEW.case_id)<>2 OR
            (SELECT count(*) FROM involves WHERE case_id=NEW.case_id)<>2))) BEGIN SELECT RAISE(ABORT,'Complete the case relationships before submission'); END;

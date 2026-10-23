-- Run once in the Neon SQL Editor to remove the tables from the old design.
-- The website now uses the EER tables (see EER_MAPPING.md). This deletes the old test data.
DROP TABLE IF EXISTS analysis_jobs, videos, vehicles, invitations, parties, cases,
    garage_vehicles, password_resets, login_failures, expert_logins, expert_accounts, users CASCADE;

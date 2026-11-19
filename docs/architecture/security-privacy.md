# Security and Privacy Design Notes (Phase 1 scope)

## Threats addressed and where they are tested
| Threat | Control | Test |
|---|---|---|
| Cross-tenant data read | Server-derived tenant + ORM tenant filter + fail-closed | `tests/test_tenant_isolation.py` (API and DB layer) |
| Cross-tenant write / tenant_id tampering | `before_flush` guard, immutable tenant_id | `test_db_layer_blocks_cross_tenant_writes`, `test_tenant_id_is_immutable` |
| BOLA / IDOR on roles, memberships | Scoped queries return 404 for foreign ids | `test_foreign_role_and_membership_ids_are_not_found` |
| Client-supplied tenant id | Ignored everywhere | `test_tenant_id_from_client_is_ignored` |
| Privilege escalation | Grant-only-what-you-hold, immutable system roles, last-owner guard | `test_hr_admin_cannot_escalate_to_owner`, `test_role_manager_cannot_grant_permissions_they_lack`, `test_cannot_remove_last_owner` |
| Missing function-level authorization | `require()` on every tenant endpoint | `test_employee_cannot_access_admin_endpoints` |
| Credential stuffing / brute force | Argon2id, lockout, uniform errors, IP rate limit, security events | `test_wrong_password_and_lockout`, `test_unknown_account_same_error_as_wrong_password` |
| Account enumeration | Identical responses on register/forgot/resend | `test_register_does_not_enumerate_accounts`, `test_forgot_password_unknown_email_is_silent` |
| Session theft / fixation | HttpOnly+SameSite cookie, hashed token at rest, server-side revoke, new token per login | `test_session_cookie_is_httponly`, `test_logout_revokes_session_server_side` |
| CSRF | HMAC-bound header token + Origin allow-list | `test_csrf_required_on_unsafe_requests`, `test_foreign_origin_blocked` |
| MFA bypass / replay | Time-step replay guard, single-use recovery codes, encrypted secret | `test_mfa_flow_with_replay_protection_and_recovery`, `test_mfa_secret_encrypted_at_rest` |
| Token reuse | Single-use hashed email/reset tokens; reset revokes all sessions | `test_password_reset_revokes_all_sessions` |
| Audit tampering | Append-only ORM guard | `test_audit_log_is_append_only` |
| Suspended tenant access | Checked on every request | `test_suspended_tenant_is_locked_out` |

## Added with the HR modules
| Threat | Control | Test |
|---|---|---|
| Unauthorized salary access | `salary.read` needed, employees and managers excluded by default | `test_salary_and_payroll_access_is_denied_to_regular_employees` |
| Payroll tampering | Locked after approval, ORM guard on entries and line items | `test_separation_of_duties_and_finalization_lock` |
| Duplicate payroll | One run per period per organization | `test_duplicate_period_is_refused_and_bad_periods_rejected` |
| Approving your own payroll, leave or correction | Creator and requester checks | payroll, leave and attendance API tests |
| Someone else's payslip | Owner-only, finalized-only, same 404 as missing | `test_payslip_privacy_and_publication` |
| Broken object-level authorization on employees | Every employee id is checked inside the tenant | `test_employees_are_isolated_between_tenants` and the isolation tests in each module |
| File access control | Authenticated download, own or `documents.manage`, audited | `test_documents_upload_download_and_access_control` |
| Malicious uploads | Type and size limits, scanner hook | `test_document_upload_validation_and_tenant_isolation` |
| Sensitive fields at rest | Fernet encryption for bank account and national ID | `test_bank_account_is_encrypted_at_rest` |
| Public endpoint abuse | Rate limiting, tenant narrowed by slug, only open jobs | `test_public_endpoints_do_not_leak_or_cross_tenants` |

## Not covered
PostgreSQL row-level security, duplicate financial transaction tests for loans and expenses (modules not built), a
malware scanner implementation, key rotation procedure for field encryption.

## Privacy
- Secrets are never in source. Production refuses a weak or default `TALVYNZA_SECRET_KEY` and the memory email backend.
- Passwords and tokens are never logged. Verification and reset tokens are stored as hashes. The console email backend
  prints one-time links and must not be used outside development.
- Retention and anonymization workflows are not implemented.

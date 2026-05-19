Sports Federation Compliance
============================

Document requirements, submissions, and compliance checking. Ensures that
clubs, players, referees, and venues maintain all required documentation
(licenses, insurance certificates, safety reports, and similar evidence).

Purpose
-------

Defines what **documents are required** for each entity type, tracks
**submissions** with attachments and expiry dates, and runs
**compliance checks** to flag missing or expired documentation.

Dependencies
------------

- ``sports_federation_base``: Clubs.
- ``sports_federation_people``: Players.
- ``sports_federation_officiating``: Referees.
- ``sports_federation_venues``: Venues.
- ``sports_federation_portal``: Club representatives.
- ``mail``: Chatter.

Models
------

``federation.document.requirement``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A type of document that certain entities must provide.

Fields:

- ``name`` (Char): Requirement title.
- ``code`` (Char): Unique code.
- ``target_model`` (Selection): Entity type such as club, player, referee,
   venue, or club representative.
- ``required_for_all`` (Boolean): Applies to all entities of that type.
- ``requires_expiry_date`` (Boolean): Submission must include an expiry date.
- ``validity_days`` (Integer): Default validity period.
- ``description`` (Text): Detailed requirements.
- ``active`` (Boolean): Whether the requirement is currently enforced.

``federation.document.submission``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An actual document submitted against a requirement.

Fields:

- ``name`` (Char): Submission title.
- ``requirement_id`` (Many2one): Requirement being fulfilled.
- ``target_model`` (Selection, computed): Copied from the requirement.
- ``club_id`` / ``player_id`` / ``referee_id`` / ``venue_id`` /
   ``club_representative_id`` (Many2one): Target entity.
- ``status`` (Selection): ``draft``, ``submitted``, ``approved``,
   ``rejected``, ``replacement_requested``, or ``expired``.
- ``attachment_ids`` (Many2many): Uploaded files.
- ``issue_date`` / ``expiry_date`` (Date): Document validity.
- ``reviewer_id`` (Many2one): Reviewer.
- ``reviewed_on`` (Datetime): Review timestamp.
- ``is_expired`` (Boolean, computed): True when ``expiry_date`` is before
   today.
- ``target_display`` (Char, computed): Readable target entity name.
- ``notes`` (Text): Remarks.

- **State machine**: ``draft -> submitted -> approved / rejected /
   replacement_requested -> expired``.
- **Constraint**: exactly one target entity field must be set.
- **Expired ribbon**: shown in the form view when the document has passed its
   expiry date.

``federation.compliance.check``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A check result linking a requirement to an entity's submission status.

Fields:

- ``name`` (Char): Check title.
- ``target_model`` (Selection): Entity type.
- ``club_id`` / ``player_id`` / ``referee_id`` / ``venue_id`` /
   ``club_representative_id`` (Many2one): Target.
- ``status`` (Selection): ``compliant``, ``missing``, ``pending``, or
   ``expired``.
- ``requirement_id`` (Many2one): Requirement being checked.
- ``submission_id`` (Many2one): Linked submission, when available.
- ``checked_on`` (Datetime): Check timestamp.
- ``note`` (Char): Result note.
- ``target_display`` (Char, computed): Readable target name.

``federation.compliance.check.archive``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Immutable history row capturing how a compliance check looked at a point in
time.

Fields:

- ``compliance_check_id`` (Many2one): Source compliance check.
- ``archived_on`` / ``checked_on`` (Datetime): Archive timestamp and source
   check timestamp.
- ``target_model`` / ``target_res_id`` (Char / Integer): Archived target
   reference.
- ``requirement_id`` / ``submission_id`` (Many2one): Requirement and linked
   submission snapshot.
- ``status`` (Selection): Archived compliance status.
- ``note`` (Char): Archived operator note.

Key Behaviours
--------------

- **Requirement definition**: federation staff define which documents each
   entity type must provide.
- **Submission workflow**: documents are uploaded, submitted, and reviewed with
   approval or rejection outcomes.
- **Expiry tracking**: computed ``is_expired`` flags overdue documents.
- **Compliance checks**: programmatic checks produce compliant, missing,
   pending, or expired statuses per entity.
- **Multi-entity support**: the same framework covers clubs, players,
   referees, venues, and club representatives.
- **Portal self-service workspace**: scoped portal users can review their own
   requirements, renewal deadlines, remediation notes, and submission history
   at ``/my/compliance``.
- **Portal submission flow**: club representatives and referees can upload
   replacement documents and submit renewals directly from the portal detail
   page without backend access. The controller delegates the write to
   ``federation.document.submission._portal_submit_submission()`` so
   attachment creation and submission state changes stay inside the model
   boundary.
- **Historical evidence**: compliance checks append archive rows on create and
   on tracked status changes so operators can review how a target moved from
   missing to compliant over time.

Portal Self-Service
-------------------

Portal routes:

- ``GET /my/compliance``: workspace listing with renewal warnings, review
   state, and attention-first sorting.
- ``GET /my/compliance/<requirement_id>/<target_model>/<target_id>``: detail
   page for one requirement and target record.
- ``POST /my/compliance/<requirement_id>/<target_model>/<target_id>/submit``:
   attachment-backed submission or renewal request.

Portal workspace behaviour:

- Access is limited to targets the current portal user is allowed to manage.
- Remediation notes from the reporting layer are surfaced when available.
- Renewal windows are highlighted before expiry so replacement documents can be
   submitted proactively.
- Attachment creation preserves portal user identity while still using
   controlled elevated writes through
   ``_portal_submit_submission()`` and
   ``_portal_create_submission_attachments()``.

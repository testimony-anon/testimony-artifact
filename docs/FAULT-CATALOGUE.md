# Fault catalogue (RQ2)

Everything here was fixed before any detection result was seen (Section IV-F of the paper). The business rules come from the functional description, the fixed source versions and the recorded UI action sequences; each seeded source fault changes one place of business logic, each injected response fault applies one fixed transformation to every matching response on the client side. Sections 1-4 cover Conduit and RWA (identifiers as used in `eval/ui_semantics/rq2-deepseek-final2-20260912/suite/`: `outcomes-*.jsonl`, `test-fault-map.jsonl`), section 5 covers Umami, Paperless-ngx and Ghost (`eval/ui_semantics/rq2-subjects-20260921/`). The `definition_ref` field of `response-faults.jsonl` points at the authors' internal design notes, which this catalogue supersedes.

## 1. Business rules of Conduit and RWA

| Rule | Statement |
|---|---|
| C01 | Registration persists the identity; a duplicate e-mail must not overwrite an existing account. |
| C02 | Correct credentials return the corresponding user; wrong credentials must not establish a session. |
| C03 | Guests can read public articles; logout, hidden buttons and client-side route guards are not server-side rejection of unauthorised requests. |
| C04 | Created content, its author and its valid tags can be read back. |
| C05 | A duplicate title (slug conflict) is rejected; the original article is not overwritten. |
| C06 | Edits persist; after a title change the new slug and reads by another user resolve to the same article. |
| C07 | After a confirmed deletion the article can no longer be read (cancelling the dialog is a UI-only branch). |
| C08 | Non-existent articles or profiles yield not-found results. |
| C09 | A comment stores its content, author and article and is visible to legitimate readers. |
| C10 | Deleting a comment as its author removes that comment; a missing delete button for others does not prove server-side authorisation. |
| C11 | Favoriting creates the association for the acting user; status, count and the user's favourites list agree. |
| C12 | Unfavoriting removes that user's association without deleting the article or other users' associations. |
| C13 | Follow/unfollow affects the designated relationship without confusing actor and target. |
| C14 | Tag, author and favorited filters each satisfy their own scope (three distinct rules). |
| C15 | Pagination: offset = page x limit; the response is the corresponding slice with a matching count. |
| C16 | "Your Feed" contains articles of followed authors; after unfollowing, new reads no longer include that author's articles through that relationship. |
| C17 | After deleting an article, tag queries no longer contain it (global tags may persist in this version). |
| C18 | After updating the public profile, the user and another user read the new values. |
| C19 | Login and identity migration after credential changes. |
| C20 | Browser-only properties (required fields, blank comments, HTML validation, logout navigation): UI-only, not in the API fault denominator. |
| R01 | Credentials and session identity are correct; server-side logout invalidates the session. |
| R02 | A new user registers and creates a first bank account; quitting onboarding creates no later business state. |
| R03 | Bank-account name, routing number and account number persist; the owner comes from the login context. |
| R04 | Bank-account queries are isolated per logged-in user. |
| R05 | Soft delete: isDeleted becomes true; the record is still listed, shown as Deleted, without a Delete button. |
| R06 | Name, e-mail and phone updates persist, and another user's search reads the new fields. |
| R07 | Search matches fixed fields and excludes the current user (fuzzy match, not exact equality). |
| R08 | A transaction stores the amount (dollars to cents), the description and both identities; both parties read the same transaction. |
| R09 | With sufficient balance the payer is debited by the transaction amount. |
| R10 | The payee is credited by the transaction amount. |
| R11 | With insufficient balance the internal top-up branch runs and the visible app balance becomes zero, not negative. |
| R12 | A request is created as pending and is not an immediate payment debit. |
| R13 | Accepting a request stores accepted; the direction of funds differs from a plain payment. |
| R14 | The status of a rejected request can be read back (its fund side effect is a specification doubt). |
| R15 | Mine = participant, Friends = contacts, Everyone = the fixed version's merge logic; the entries do not share one scope. |
| R16 | Date and amount filters, their combination and their clearing. |
| R17 | Pagination slices by page and limit. |
| R18 | A like stores its transaction and user and legitimate reads contain it (UI double-click prevention does not prove backend idempotence). |
| R19 | Comment content, author and transaction are consistent; several comments read back independently. |
| R20 | Payment and request notifications reference the same transaction with the right recipient and type. |
| R21 | Third-party comments and likes propagate to the transaction's participants; notifications reference the same transaction and interaction. |
| R22 | The unread list contains only the current user's unread items; clearing does not delete transactions, comments or likes. |
| R23 | Browser form validation, drawers and routes: UI-only. |

## 2. Seeded source faults of Conduit and RWA (42; patches in `eval/ui_semantics/rq2-20260907/patches/`)

| Fault | Subject | Rule(s) | Location | One local change |
|---|---|---|---|---|
| B-C01 | conduit | C04 | `controllers/articles.js: createArticle` | appends a fixed non-empty string to the persisted body; title, slug and author unchanged |
| B-C02 | conduit | C04, C14 | `createArticle, tagList loop` | omits the article.addTagList association for new tags (the tags are still created) |
| B-C03 | conduit | C06 | `controllers/articles.js: updateArticle` | omits the body update assignment; other fields save normally |
| B-C04 | conduit | C07, C17 | `controllers/articles.js: deleteArticle` | omits article.destroy while keeping the response path |
| B-C05 | conduit | C09 | `controllers/comments.js: createComment` | deterministically rewrites comment.body on storage; author and article unchanged |
| B-C06 | conduit | C10 | `controllers/comments.js: deleteComment` | omits comment.destroy |
| B-C07 | conduit | C11 | `controllers/favorites.js: favoriteToggler (POST branch)` | omits article.addUser |
| B-C08 | conduit | C12 | `favoriteToggler (DELETE branch)` | omits article.removeUser |
| B-C09 | conduit | C13 | `controllers/profiles.js: followToggler (POST branch)` | omits profile.addFollower |
| B-C10 | conduit | C13 | `followToggler (DELETE branch)` | omits profile.removeFollower |
| B-C11 | conduit | C14 | `controllers/articles.js: allArticles, tag include` | drops the existing tag.name filter |
| B-C12 | conduit | C14 | `allArticles, author include` | drops the existing author.username filter |
| B-C13 | conduit | C14 | `allArticles, favorited branch` | returns the plain article list instead of the target user's favourites (same response container) |
| B-C14 | conduit | C16 | `controllers/articles.js: articlesFeed` | drops the author scope derived from the following relation |
| B-C15 | conduit | C15 | `controllers/articles.js: allArticles` | offset fixed to 0; limit and ordering unchanged |
| B-C16 | conduit | C18 | `controllers/user.js: updateUser field loop` | skips writing the bio field only |
| H-C01 | conduit | C01 | `users.signUp duplicate-e-mail guard` | removes the duplicate check (database uniqueness verified separately) |
| H-C03 | conduit | C05 | `articles.createArticle duplicate-slug guard` | removes the duplicate-title protection |
| B-R01 | rwa | R03 | `database.createBankAccountForUser` | fixed non-empty rewrite of bankName on storage |
| B-R02 | rwa | R04 | `graphql/resolvers/Query.ts: listBankAccount` | drops the ctx.user.id scope and returns all accounts |
| B-R03 | rwa | R05 | `database.removeBankAccountById` | omits persisting isDeleted = true (no hard delete) |
| B-R04 | rwa | R06 | `database.updateUserById` | skips the firstName update only |
| B-R05 | rwa | R07 | `user-routes.ts: /search` | omits removeUserFromResults; the fuzzy search itself is kept |
| B-R06 | rwa | R08 | `database.createTransaction, amount` | drops the x100 dollars-to-cents conversion |
| B-R07 | rwa | R08 | `database.createTransaction, description` | fixed rewrite of the description; transaction id unchanged |
| B-R08 | rwa | R09 | `createTransaction, payment branch` | omits debitPayAppBalance(sender, transaction) |
| B-R09 | rwa | R10 | `createTransaction, payment branch` | omits creditPayAppBalance(receiver, transaction) |
| B-R10 | rwa | R11 | `database.resetPayAppBalance` | the insufficient-balance branch keeps 1 cent instead of zeroing; the bank top-up call is unchanged |
| B-R11 | rwa | R12 | `createTransaction, requestStatus` | a new request is created as accepted instead of pending |
| B-R12 | rwa | R13 | `database.updateTransactionById, final assign` | discards the submitted requestStatus update (old status kept); funds logic untouched |
| B-R13 | rwa | R15 | `database.getAllTransactionsForUserByObj` | drops the receiverId participant branch (Mine misses transactions where the user is the payee) |
| B-R14 | rwa | R15 | `database.getTransactionsForUserContacts` | returns an empty contacts transaction set (valid array; the public merge code is unchanged) |
| B-R15 | rwa | R16 | `database.transactionsWithinDateRange` | skips filtering for requests with a complete valid date range |
| B-R16 | rwa | R16 | `database.transactionsWithinAmountRange` | skips filtering for requests with complete non-zero bounds |
| B-R17 | rwa | R17 | `utils/transactionUtils.ts: getPaginatedItems` | offset fixed to 0; pageData computation kept |
| B-R18 | rwa | R18 | `database.getLikesByTransactionId` | returns an empty likes set on read (a query fault, not a persistence fault) |
| B-R19 | rwa | R19 | `database.createComment` | fixed rewrite of the content on storage; identities and transaction unchanged |
| B-R20 | rwa | R20 | `createTransaction, payment branch` | omits creating the received-payment notification; transaction and funds are updated |
| B-R21 | rwa | R21 | `database.createLikes` | omits the receiver notification in the two-recipient branch |
| B-R22 | rwa | R21 | `database.createComments` | omits the receiver notification in the two-recipient branch |
| B-R23 | rwa | R22 | `database.getUnreadNotificationsByUserId` | keeps userId but drops isRead = false, so cleared notifications are read |
| B-R24 | rwa | R22 | `database.updateNotificationById` | omits persisting the notification edits; transactions, comments and likes untouched |

## 3. Injected response faults of Conduit and RWA (35 instances; definitions in `suite/response-faults.jsonl`)

| Fault | Subject | Field | Operator | Applied to responses of | Rule(s) | Transformation |
|---|---|---|---|---|---|---|
| PR-C01 | conduit | `user.username` | rewrite | register, login, current_user | C01, C02 | user.username in the register/login/current-user response is rewritten to another non-empty string (token and password untouched) |
| PR-C02 | conduit | `article.body` | rewrite | create | C04 | after creation, article.body in the GET response is deterministically rewritten (slug and author unchanged) |
| PR-C03 | conduit | `article.tagList` | remove_lexical_first | nonempty_tags | C04 | one existing valid tag is removed from article.tagList |
| PR-C04 | conduit | `article.body` | old_value | edit | C06 | after an edit, article.body in the GET response reverts to the pre-edit content of the same resource |
| PR-C05 | conduit | `articles` | restore_deleted | delete | C07 | after a deletion, the list response re-includes the deleted article |
| PR-C06 | conduit | `comment.body` | rewrite | create_comment | C09 | in the comments GET, the target comment.body is rewritten (identity and author unchanged) |
| PR-C07 | conduit | `comments` | restore_deleted | delete_comment | C10 | after deleting a comment, the comments GET re-inserts the deleted comment |
| PR-C08 | conduit | `article.favorited` | flip | favorite, unfavorite | C11, C12 | after favorite/unfavorite, article.favorited is flipped in one observation |
| PR-C09 | conduit | `article.favoritesCount` | add_one | favorite, unfavorite | C11, C12 | at the same position, article.favoritesCount is increased by 1 |
| PR-C10 | conduit | `profile.following` | flip | follow, unfollow | C13 | after follow/unfollow, profile.following is flipped |
| PR-C11 | conduit | `articles` | insert_outside_filter | tag | C14 | a tag-filtered list gains an existing article that lacks the requested tag |
| PR-C12-author | conduit | `articles` | insert_outside_filter | author | C14 | an author- or favorited-filtered list gains an existing article that does not satisfy the filter |
| PR-C12-favorited | conduit | `articles` | insert_outside_filter | favorited | C14 | an author- or favorited-filtered list gains an existing article that does not satisfy the filter |
| PR-C13 | conduit | `articles` | first_page | nonfirst_page | C15 | a non-first page is replaced by the first-page slice of the same limit |
| PR-C14-feed | conduit | `articles` | remove_identity_first | feed | C16, C18 | the feed misses one due article, or profile.bio reverts to the pre-update value (two operators, per route) |
| PR-C14-bio | conduit | `profile.bio` | old_value | update_profile | C16, C18 | the feed misses one due article, or profile.bio reverts to the pre-update value (two operators, per route) |
| PR-R01 | rwa | `user.username` | rewrite | check_auth | R01 | /checkAuth: a non-secret public identity field of the logged-in user is rewritten |
| PR-R02 | rwa | `account.bankName` | rewrite | list_bank_account | R03 | GraphQL bank-account read-back: bankName is rewritten (id, type and other fields kept) |
| PR-R03 | rwa | `listBankAccount` | insert_other_user | list_bank_account | R04 | listBankAccount gains another user's existing account |
| PR-R04 | rwa | `account.isDeleted` | false | soft_delete | R05 | after deletion, the account's isDeleted is changed from true to false |
| PR-R05 | rwa | `user.firstName` | old_value | update_user | R06 | after an update, public user/search responses revert firstName to the old value |
| PR-R06 | rwa | `results` | insert_self | search | R07 | search results gain the current user's own public record |
| PR-R07 | rwa | `transaction.amount` | add_one | read_transactions | R08 | transaction.amount is increased by 1 cent |
| PR-R08 | rwa | `transaction.description` | rewrite | read_transactions | R08 | transaction.description is deterministically rewritten |
| PR-R09-sender | rwa | `user.balance` | add_one | payment_sender | R09-R11 | after a payment, one user's balance is increased by 1 cent (sender and receiver instantiated separately) |
| PR-R09-receiver | rwa | `user.balance` | add_one | payment_receiver | R09-R11 | after a payment, one user's balance is increased by 1 cent (sender and receiver instantiated separately) |
| PR-R10 | rwa | `transaction.requestStatus` | enum_toggle | pending_to_accepted, accepted_to_pending | R12, R13 | a request's requestStatus is replaced within the valid pending/accepted enumeration |
| PR-R11-participant | rwa | `results` | insert_outside_filter | participant | R15, R16 | a transaction list gains an existing transaction that violates the participant, date or amount filter (each filter separately) |
| PR-R11-date | rwa | `results` | insert_outside_filter | date | R15, R16 | a transaction list gains an existing transaction that violates the participant, date or amount filter (each filter separately) |
| PR-R11-amount | rwa | `results` | insert_outside_filter | amount | R15, R16 | a transaction list gains an existing transaction that violates the participant, date or amount filter (each filter separately) |
| PR-R12 | rwa | `results` | first_page | nonfirst_page | R17 | a later page is replaced by the first-page slice of equal length |
| PR-R13-likes | rwa | `transaction.likes` | remove_action_member | like | R18, R19 | transaction read-back: one target like or comment is removed (two collections separately) |
| PR-R13-comments | rwa | `transaction.comments` | remove_action_member | comment | R18, R19 | transaction read-back: one target like or comment is removed (two collections separately) |
| PR-R14 | rwa | `results` | remove_effect_notification | payment, request, like, comment | R20, R21 | notifications GET: one notification for this transaction or interaction is removed |
| PR-R15 | rwa | `results` | restore_cleared | clear_notification | R22 | after clearing, the unread list re-includes the notification just cleared |

## 4. Cross-flow compositions of Conduit and RWA (17; schedules in `suite/compositions.jsonl`)

| Composition | Subject | Rules | Sequences | Schedule and checks | Targets confirmed defect |
|---|---|---|---|---|---|
| C-C01 | conduit | C06, C11-C12, C14 | L4-EDIT-01, L4-FAVORITE-01 | A publishes; B favorites; A edits the same article; B reads favourites/detail; B unfavorites. The earlier favourite still points to the same article after the edit; counts change only through that user's actions. | - |
| C-C02 | conduit | C06, C09-C10 | L4-COMMENT-01, L4-EDIT-01 | A publishes; B comments; A edits; both read comments; B deletes the comment. Body edits do not delete others' comments; deleting a comment does not roll back the article. | - |
| C-C03 | conduit | C07, C13, C16 | L4-FOLLOW-01, L4-PUBLISH-01, L4-DELETE-01 | B follows A; A publishes; B reads the feed; A deletes; B reads the feed; B unfollows. Follow state and article lifecycle are independent. | - |
| C-C04 | conduit | C07, C09, C11, C17 | L4-FAVORITE-01, L4-COMMENT-01, L4-DELETE-01, L2-TAG-01 | A publishes with tags; B favorites/comments; A deletes; list, detail and tag queries. The deleted article is not returned; global tag deletion is not assumed. | - |
| C-C05 | conduit | C04, C09, C18 | L2-SETTINGS-01, L4-PUBLISH-01, L4-COMMENT-01 | A publishes; B comments; A changes only bio/image; B re-reads the author profile and content. The profile refresh loses no articles or comments. | - |
| C-C06 | conduit | C04, C17 | L1-ARTICLE-07 | After the recorded creation the article and /api/tags are read and the submitted tags are compared. | D5 |
| C-C07 | conduit | C04 | L1-ARTICLE-07 | The created article is read immediately five times without settling. | D6 |
| C-R01 | rwa | R06-R10 | L4-SETTINGS-SEARCH-01, L3-PAYMENT-01 | A updates the public profile; B searches A by the new fields; B pays A; both read back. New fields do not redirect funds to another identity. | - |
| C-R02 | rwa | R08-R10, R18-R22 | L4-PAYMENT-NOTIFY-01, L4-THIRD-PARTY-COMMENT-01, L4-THIRD-PARTY-LIKE-01 | One transaction; third-party interactions; participants read and clear notifications one by one; the transaction is re-read. Clearing deletes no interaction and repeats no transfer. | - |
| C-R03 | rwa | R08-R10, R15-R17 | L2-PAYMENT-01, L4-PAYMENT-FEEDS-01, L1-FEED-04 | Two valid payments; both read Mine; date and amount filters; filters cleared. | - |
| C-R04 | rwa | R03-R05, R08-R10 | L3-BANK-01, L3-PAYMENT-01 | A non-essential bank account is created and soft-deleted; a payment is made from the existing sufficient app balance; both parties' accounts and transactions are read. | - |
| C-R05 | rwa | R12-R13, R18-R22 | L3-REQUEST-ACCEPT-01, L4-REQUEST-NOTIFY-01, L3-COMMENT-01 | A requests; B accepts once; both interact; notifications are cleared; status and balances are re-read. No repeated settlement, no rollback of accepted. | - |
| C-R06 | rwa | R12-R14 | L3-REQUEST-REJECT-01 | Balances and the transaction status are read before and after the recorded reject. | D1 |
| C-R07 | rwa | R13 | L3-REQUEST-ACCEPT-01 | A second identical accept after the recorded accept; balances compared. | D2 |
| C-R08 | rwa | R22 | L1-NOTIFY-01 | The other actor PATCHes the owner's notification after the recorded request update. | D3 |
| C-R09 | rwa | R21 | L4-LIKE-NOTIFY-01 | The actor likes and comments its own new payment before the recorded accept; the actor's own notifications are compared. | D4 |
| C-R10 | rwa | R01, R04 | L3-REQUEST-REJECT-01 | After the original checks the actor logs out and repeats ListBankAccount. | D7 |

## 5. Faults of Umami, Paperless-ngx and Ghost (21)

The same registry format and the same protocol: designed from the functional description, the pinned source version and the recorded UI action sequences, frozen before any detection result was seen, and evaluated with the pairing, the O0/O1/O2 projection and the business-only and unknown definitions of Section IV-F. Umami has response faults only: its subject is a pre-built image and no source tree was available on the machine, so no source fault could be laid over it. Identifiers, registry rows and per-fault outcomes are in `eval/ui_semantics/rq2-subjects-20260921/` (`inputs/faults-<subject>.jsonl` with the frozen copies `inputs/faults-<subject>.frozen-*.jsonl.bak`, `suite/outcomes-*.jsonl`, `suite/report-<subject>.md`); the registry format is specified in `inputs/FAULT-CATALOG-SPEC.md`.

### 5.1 Umami 3.4.0 (0 source, 4 response)

| Fault | Kind | Module | Business rule | One local change / operator | Routes | Activated by |
|---|---|---|---|---|---|---|
| PR-U01 | response | website | A website created by the signed-in user must appear in that user's websites list (GET /api/users/{userId}/websites), which is what the Websites page and the Settings > Websites table render. | `omit_created_member` {"id_field": "id", "list_path": "$.data"} — Remove from the data array of every successful GET /api/users/{userId}/websites response each member whose id is a website id created by POST /api/websites in this epoch; count, page, pageSize, orderBy and all other members are left untouched. | trigger write: `POST /api/websites` (create); reads: `GET /api/users/[^/]+/websites` | L1-WEBSITE-01, L3-TEAM-04 |
| PR-U02 | response | website | A deleted website must no longer appear in its owner's websites list (GET /api/users/{userId}/websites). | `reinsert_deleted_member` {"id_field": "id", "list_path": "$.data"} — Re-insert into the data array of every successful GET /api/users/{userId}/websites response the last observed website object whose id was deleted by DELETE /api/websites/{id} in this epoch; count and the other fields are left untouched. | trigger write: `DELETE /api/websites/[^/]+` (delete); reads: `GET /api/users/[^/]+/websites` | L1-WEBSITE-03, L1-WEBSITE-04 |
| PR-U03 | response | share | A share (public report link) created for a website is stored and read back with exactly the name entered; the Shares table of the website settings page (GET /api/websites/{websiteId}/shares) shows that name. | `rewrite_string` {"field": "name", "id_field": "id", "scope": "created"} — Append the fixed suffix ' [RQ2]' to the name of every share object, in any successful GET /api/websites/{websiteId}/shares response, whose id was created by POST /api/websites/{websiteId}/shares in this epoch; id, entityId, slug, shareType and parameters are left untouched. | trigger write: `POST /api/websites/[^/]+/shares` (create); reads: `GET /api/websites/[^/]+/shares` | L1-SHARE-01, L2-SHARE-02 |
| PR-U04 | response | user | A role change saved by an administrator for a user (POST /api/users/{id}) must be read back on that user's detail (GET /api/users/{id}) and in the admin users list. | `old_value_after_update` {"field": "role", "id_field": "id"} — For every successful GET /api/users/{id} or GET /api/admin/users response, replace the role of the user object whose id was targeted by POST /api/users/{id} in this epoch with the role value last observed before that write, when it differs from the current value; id, username, createdAt and twoFactorRequired are left untouched. | trigger write: `POST /api/users/[^/]+` (update); reads: `GET /api/users/[^/]+`, `GET /api/admin/users` | L1-USER-04, L3-USER-05, L2-USER-02 |

### 5.2 Paperless-ngx 3.2.0 (3 source, 3 response)

| Fault | Kind | Module | Business rule | One local change / operator | Routes | Activated by |
|---|---|---|---|---|---|---|
| B-P01 | source | documents | Saving a document with a new title persists that title: PATCH/PUT /api/documents/{id}/ with `title` changes the stored title, and every later read of the document (GET /api/documents/{id}/, the same object in GET /api/documents/) returns the new title. | documents/serialisers.py DocumentSerializer.update(): the submitted `title` is dropped from validated_data before the document is saved (one inserted line); every other field is saved normally and the request still answers 200 with the document, but the stored title never changes. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-P01/serialisers.py`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-P01.patch`, laid read-only over `/usr/src/paperless/src/documents/serialisers.py` in the image (original SHA-256 `7ad1bee65cd65e78…`). | pairing route(s): `PATCH /api/documents/\d+`, `PUT /api/documents/\d+`; affected reads: `GET /api/documents/\d+`, `GET /api/documents` | L2-DOCEDIT-01 (L2-DOCEDIT-03 patches the same route without a title and pairs without activating) |
| B-P02 | source | notes | Deleting a note removes it: DELETE /api/documents/{id}/notes/?id=N answers with the remaining notes, and the note no longer appears in any later read (GET /api/documents/{id}/notes/, the `notes` array of GET /api/documents/{id}/ and of the document list). | documents/views.py DocumentViewSet.notes(), DELETE branch: the `note.delete()` call is omitted (the audit-log entry, the document `modified` bump and the index update are kept), so the request still answers 200 with the notes list but the note stays stored and listed. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-P02/views.py`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-P02.patch`, laid read-only over `/usr/src/paperless/src/documents/views.py` in the image (original SHA-256 `6000bf1814bd87fa…`). | pairing route(s): `DELETE /api/documents/\d+/notes`; affected reads: `GET /api/documents/\d+/notes`, `GET /api/documents/\d+`, `GET /api/documents` | L2-DOCEDIT-02 |
| B-P03 | source | bulk_edit | A bulk tag edit applies to every selected document: POST /api/documents/bulk_edit/ {method: modify_tags, documents: [...], parameters: {add_tags, remove_tags}} adds the tags to all listed documents, so each of them lists the tag afterwards (GET /api/documents/, GET /api/documents/{id}/) and the tag's document_count grows by the number of selected documents. | documents/bulk_edit.py modify_tags(): the affected document set is built from `doc_ids[:1]` instead of `doc_ids`, so only the first document of the submitted selection receives (or loses) the tags while the response stays {"result": "OK"}. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-P03/bulk_edit.py`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-P03.patch`, laid read-only over `/usr/src/paperless/src/documents/bulk_edit.py` in the image (original SHA-256 `6b0b7b4542db54d7…`). | pairing route(s): `POST /api/documents/bulk_edit`; affected reads: `GET /api/documents`, `GET /api/documents/\d+`, `GET /api/tags`, `POST /api/documents/selection_data` | L1-DOCLIST-06 |
| PR-P01 | response | documents | After a document update, reading the document returns the updated title. | `old_value_after_update` {"field": "title", "id_field": "id"} — For a document targeted by a PATCH /api/documents/{id}/ of this epoch, every later 2xx GET /api/documents/{id}/ (and the same object inside GET /api/documents/) reports the `title` last observed before the update instead of the current one. | trigger write: `PATCH /api/documents/\d+` (update); reads: `GET /api/documents/\d+`, `GET /api/documents` | L2-DOCEDIT-01 (L2-DOCEDIT-03 does not change the title) |
| PR-P02 | response | tags | A newly created tag appears in the tag list: after POST /api/tags/ answers 201 with the new tag, GET /api/tags/ lists it for its owner and for every user allowed to view it. | `omit_created_member` {"id_field": "id", "list_path": "$.results"} — Every 2xx GET /api/tags/ response of the epoch has the members whose `id` was created by a POST /api/tags/ of this epoch removed from `$.results` (count and display_count are left as they are). | trigger write: `POST /api/tags` (create); reads: `GET /api/tags` | L3-SHARING-01, L3-SHARING-02 |
| PR-P03 | response | users | Saving a user's permissions persists them: after PUT /api/users/{id}/ with `user_permissions`, GET /api/users/ (and GET /api/users/{id}/) returns the new permission list for that user. | `old_value_after_update` {"field": "user_permissions", "id_field": "id"} — For a user targeted by a PUT /api/users/{id}/ of this epoch, every later 2xx GET /api/users/{id}/ and the matching object inside GET /api/users/ report the `user_permissions` list last observed before the update instead of the current one. | trigger write: `PUT /api/users/\d+` (update); reads: `GET /api/users/\d+`, `GET /api/users` | L3-SHARING-01, L3-SHARING-02 |

### 5.3 Ghost 5.130.6 (5 source, 6 response)

| Fault | Kind | Module | Business rule | One local change / operator | Routes | Activated by |
|---|---|---|---|---|---|---|
| B-G01 | source | posts | The post access level (visibility: public / members / paid) chosen in the post settings menu is persisted by the post update and returned by every later read of that post. | PostsService.editPost drops the submitted `visibility` attribute before calling Post.edit, so PUT posts/{id} still answers 200 with the post envelope but the stored visibility (and every later read) keeps its previous value. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-G01/PostsService.js`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-G01.patch`, laid read-only over `/var/lib/ghost/versions/5.130.6/core/server/services/posts/PostsService.js` in the image (original SHA-256 `34916ddacc486c5d…`). | pairing route(s): `PUT /ghost/api/admin/posts/[0-9a-f]{24}/?`; affected reads: `GET /ghost/api/admin/posts/?`, `GET /ghost/api/admin/posts/[0-9a-f]{24}/?` | L1-POST-04, L1-POST-05 |
| B-G02 | source | members | Deleting a member removes it: after DELETE members/{id} the member is absent from the members list and detail reads and the member counts drop accordingly. | MemberRepository.destroy returns the fetched member instead of calling Member.destroy, so DELETE members/{id} still answers 204 but the member row stays in the database. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-G02/MemberRepository.js`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-G02.patch`, laid read-only over `/var/lib/ghost/versions/5.130.6/core/server/services/members/members-api/repositories/MemberRepository.js` in the image (original SHA-256 `7af02efb1e40f341…`). | pairing route(s): `DELETE /ghost/api/admin/members/[0-9a-f]{24}/?`; affected reads: `GET /ghost/api/admin/members/?`, `GET /ghost/api/admin/members/[0-9a-f]{24}/?`, `GET /ghost/api/admin/members/stats/count/?`, `GET /ghost/api/admin/stats/member_count/?` | L2-MEMBER-03 |
| B-G03 | source | settings | Every setting submitted in one PUT settings/ batch (title and description, or meta_title and meta_description) is persisted and returned by the following settings reads. | SettingsBREADService.edit hands only the first element of the submitted batch to Settings.edit (`refilteredSettings.slice(0, 1)`), so the write still answers 200 with the full settings list but the second and later keys keep their old values. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-G03/SettingsBREADService.js`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-G03.patch`, laid read-only over `/var/lib/ghost/versions/5.130.6/core/server/services/settings/SettingsBREADService.js` in the image (original SHA-256 `b6634eec1f0c644f…`). | pairing route(s): `PUT /ghost/api/admin/settings/?`; affected reads: `GET /ghost/api/admin/settings/?`, `GET /ghost/api/admin/site/?` | L1-SETTING-01, L1-SETTING-02 |
| PR-G01 | response | posts | A post created in this epoch appears in the posts list reads that select it (Published tab, filter=id:<id>, filter=status:published). | `omit_created_member` {"id_field": "id", "list_path": "$.posts"} — Every 2xx GET /ghost/api/admin/posts/ response has the members of $.posts whose id was created by a POST /ghost/api/admin/posts/ of this epoch removed. | trigger write: `POST /ghost/api/admin/posts/?` (create); reads: `GET /ghost/api/admin/posts/?` | L1-POST-01, L1-POST-04, L1-POST-05, L2-POST-03, L2-POST-10, L2-AUTHOR-03, L2-PERM-02 |
| PR-G02 | response | posts | After a post or page is published (PUT with status=published) every later read of that post or page reports status 'published'. | `old_value_after_update` {"field": "status", "id_field": "id"} — In every 2xx read of posts or pages (list or detail) the object whose id was targeted by a PUT of this epoch gets its `status` replaced by the value last observed before that PUT ('draft' in the recorded publish flows) whenever it differs from the current value. | trigger write: `PUT /ghost/api/admin/posts/[0-9a-f]{24}/?` (update), `PUT /ghost/api/admin/pages/[0-9a-f]{24}/?` (update); reads: `GET /ghost/api/admin/posts/?`, `GET /ghost/api/admin/posts/[0-9a-f]{24}/?`, `GET /ghost/api/admin/pages/?`, `GET /ghost/api/admin/pages/[0-9a-f]{24}/?` | L1-POST-01, L1-POST-04, L1-POST-05, L2-POST-03, L2-POST-10, L2-AUTHOR-03, L2-PERM-02, L1-PAGE-01 |
| PR-G03 | response | members | A member deleted in this epoch does not appear in later members list reads. | `reinsert_deleted_member` {"id_field": "id", "list_path": "$.members"} — Every 2xx GET /ghost/api/admin/members/ response gets, for each member id deleted by a DELETE /ghost/api/admin/members/{id} of this epoch, the last observed object of that member re-inserted into $.members. | trigger write: `DELETE /ghost/api/admin/members/[0-9a-f]{24}/?` (delete); reads: `GET /ghost/api/admin/members/?` | L2-MEMBER-03 |
| B-G04 | source | posts | A column projection (fields=) must not change which posts a browse returns: GET posts/ returns posts (type:post) and never pages, whatever projection is requested. | In the posts input serializer's browse step, reads that carry a column projection (fields= -> frame.options.columns) get their forced type condition rewritten from type:post to type:page, so projected reads such as the dashboard's fields=id,url,title,visibility,published_at return the published pages while the same read without fields returns the posts. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-G04/posts.js`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-G04.patch`, laid read-only over `/var/lib/ghost/versions/5.130.6/core/server/api/endpoints/utils/serializers/input/posts.js` in the image (original SHA-256 `b82f449b6a533122…`). | pairing route(s): `GET /ghost/api/admin/posts/?` | the dashboard read `GET posts/?…&fields=…` (recorded 44x in 19 sequences) |
| B-G05 | source | posts | The admin search index for posts (GET search-index/posts/) lists posts (type:post) only; pages have their own index (search-index/pages/), and the posts index agrees with GET posts/ on which posts exist. | api/endpoints/search-index.js fetchPosts builds its query with the pages condition filter: 'type:page' (a copy of fetchPages) instead of 'type:post', so GET search-index/posts/ returns the published pages instead of the posts; search-index/pages/ and GET posts/ are unchanged. Patched file `eval/ui_semantics/rq2-subjects-20260921/patches/B-G05/search-index.js`, diff `eval/ui_semantics/rq2-subjects-20260921/patches/B-G05.patch`, laid read-only over `/var/lib/ghost/versions/5.130.6/core/server/api/endpoints/search-index.js` in the image (original SHA-256 `3c77f429c845e57c…`). | pairing route(s): `GET /ghost/api/admin/search-index/posts/?` | `GET search-index/posts/` (recorded 22x in 19 sequences) |
| PR-G04 | response | posts | A column projection (fields=) must not change which posts a read returns: the posts listed by a projected read are the posts listed by the same read without the projection. | `omit_first_member` {"id_field": "id", "list_path": "$.posts", "when_query_key": "fields"} — Every 2xx GET /ghost/api/admin/posts/ response whose query string contains the key fields loses the member of $.posts with the smallest id; reads without fields are untouched (no trigger write). | no trigger write (a read/query rule); reads: `GET /ghost/api/admin/posts/?` | every `GET posts/` read that carries `fields` (the dashboard read, recorded 44x in 19 sequences) |
| PR-G05 | response | newsletters | Asking for relation counts (include=count.active_members) must not change which newsletters a read returns: the newsletters listed with include are the newsletters listed without it. | `drop_last_member` {"list_path": "$.newsletters", "when_query_key": "include"} — Every 2xx GET /ghost/api/admin/newsletters/ response whose query string contains the key include loses the last member of $.newsletters; reads without include (filter=status:active) are untouched (no trigger write). | no trigger write (a read/query rule); reads: `GET /ghost/api/admin/newsletters/?` | every `GET newsletters/` read that carries `include` (recorded 50x) |
| PR-G06 | response | posts | An explicit sort order (order=) must not alter the members it sorts: a post reads back with the same title whether or not the read specifies order. | `rewrite_string` {"field": "title", "scope": "all", "when_query_key": "order"} — Every 2xx GET /ghost/api/admin/posts/ response whose query string contains the key order has the fixed suffix ' [RQ2]' appended to the title of every post object; reads without order are untouched (no trigger write). | no trigger write (a read/query rule); reads: `GET /ghost/api/admin/posts/?` | every `GET posts/` read that carries `order` (the dashboard and post-list reads, recorded 65x) |

### 5.4 The read and query rules of the Ghost registry

The first six Ghost faults (B-G01..B-G03, PR-G01..PR-G03) target the effects of writes. After the registration step paired them with the qualified tests it became visible that the Ghost test suite contains almost no writes: of its 739 qualified tests, 563 are read-to-read query relations and 176 are single-response checks, and the only writes in the plans are 7 `POST members/` and the settings `PUT`. Five further faults were therefore designed from the read and query rules that the recorded reads exercise — B-G04 and B-G05 (wrong query condition in the source: a column-projected browse and the posts search index are restricted to the page type) and PR-G04..PR-G06 (response faults with no trigger write, gated on a query key: `fields`, `include`, `order`). The first six faults stay in the denominator of the reported results.


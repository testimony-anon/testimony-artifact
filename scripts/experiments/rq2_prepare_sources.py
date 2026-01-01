"""Build isolated RQ2 source versions; never starts a subject or edits its original checkout."""
from __future__ import annotations

import argparse
import re
import difflib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "eval/ui_semantics/rq2-20260907"
RWA_ORIGINAL = Path("<SUBJECTS>/cypress-realworld-app")
NORMAL_IMAGE = "uisemtest-rq2-normal:20260907"

# Each replacement is unique within one pinned source file. Strings/units were
# chosen before fault outcomes, not by inspecting an assertion's expected value.
SPECS: list[tuple[str, str, str, str]] = []
def spec(fid: str, path: str, old: str, new: str) -> None:
    SPECS.append((fid, path, old, new))

CA = "backend/controllers/articles.js"
spec("B-C01", CA, "      body: body,", '      body: body + "_rq2",')
spec("B-C02", CA, "        await article.addTagList(newTag);", "        // RQ2: omit linking the new tag.")
spec("B-C03", CA, "    if (body) article.body = body;", "    // RQ2: omit article body update.")
spec("B-C04", CA, "    await article.destroy();", "    // RQ2: omit article deletion.")
spec("B-C05", "backend/controllers/comments.js", "      body: body,", '      body: body + "_rq2",')
spec("B-C06", "backend/controllers/comments.js", "    await comment.destroy();", "    // RQ2: omit comment deletion.")
spec("B-C07", "backend/controllers/favorites.js", '    if (req.method === "POST") await article.addUser(loggedUser);', "    // RQ2: omit adding favorite.")
spec("B-C08", "backend/controllers/favorites.js", '    if (req.method === "DELETE") await article.removeUser(loggedUser);', "    // RQ2: omit removing favorite.")
spec("B-C09", "backend/controllers/profiles.js", "      await profile.addFollower(loggedUser);", "      // RQ2: omit adding follower.")
spec("B-C10", "backend/controllers/profiles.js", "      await profile.removeFollower(loggedUser);", "      // RQ2: omit removing follower.")
spec("B-C11", CA, "          ...(tag && { where: { name: tag } }),", "          // RQ2: omit tag filter.")
spec("B-C12", CA, "          ...(author && { where: { username: author } }),", "          // RQ2: omit author filter.")
spec("B-C13", CA, "      articles.rows = await user.getFavorites(searchOptions);\n      articles.count = await user.countFavorites();", "      articles = await Article.findAndCountAll(searchOptions);")
spec("B-C14", CA, "      where: { userId: authors.map((author) => author.id) },", "      // RQ2: omit followed-author scope.")
spec("B-C15", CA, '      offset: offset * limit,\n      order: [["createdAt", "DESC"]],\n    };', '      offset: 0,\n      order: [["createdAt", "DESC"]],\n    };')
spec("B-C16", "backend/controllers/user.js", '      if (value !== undefined && key !== "password") loggedUser[key] = value;', '      if (value !== undefined && key !== "password" && key !== "bio") loggedUser[key] = value;')
spec("H-C01", "backend/controllers/users.js", '    if (userExists) throw new AlreadyTakenError("Email", "try logging in");', "    // RQ2: omit duplicate-email guard.")
spec("H-C03", CA, '    if (slugInDB) throw new AlreadyTakenError("Title");', "    // RQ2: omit duplicate-title guard.")

RD = "backend/database.ts"
spec("B-R01", RD, "    bankName: accountDetails.bankName!,", '    bankName: accountDetails.bankName! + "_rq2",')
spec("B-R02", "backend/graphql/resolvers/Query.ts", 'import { getBankAccountsByUserId } from "../../database";', 'import { getAllForEntity } from "../../database";')
# B-R02 has a second mechanical import/use edit implementing one query-scope fault.
EXTRA = {"B-R02": ("return getBankAccountsByUserId(ctx.user.id);", 'return getAllForEntity("bankaccounts");')}
spec("B-R03", RD, "    .assign({ isDeleted: true }) // soft delete", "    // RQ2: omit soft-delete assignment")
spec("B-R04", RD, "  db.get(USER_TABLE).find(user).assign(edits).write();", "  const { firstName: _ignoredFirstName, ...remainingEdits } = edits;\n  db.get(USER_TABLE).find(user).assign(remainingEdits).write();")
spec("B-R05", "backend/user-routes.ts", "  const users = removeUserFromResults(req.user?.id!, searchUsers(q as string));", "  const users = searchUsers(q as string);")
spec("B-R06", RD, "    amount: transactionDetails.amount * 100,", "    amount: transactionDetails.amount,")
spec("B-R07", RD, "    description: transactionDetails.description,", '    description: transactionDetails.description + "_rq2",')
spec("B-R08", RD, "    debitPayAppBalance(sender, transaction);", "    // RQ2: omit payer debit.")
spec("B-R09", RD, "    creditPayAppBalance(receiver, transaction);", "    // RQ2: omit recipient credit.")
spec("B-R10", RD, "export const resetPayAppBalance = constant(0);", "export const resetPayAppBalance = constant(1);")
spec("B-R11", RD, 'requestStatus: transactionType === "request" ? TransactionRequestStatus.pending : undefined,', 'requestStatus: transactionType === "request" ? TransactionRequestStatus.accepted : undefined,')
spec("B-R12", RD, "  db.get(TRANSACTION_TABLE).find(transaction).assign(edits).write();", "  const { requestStatus: _ignoredRequestStatus, ...remainingEdits } = edits;\n  db.get(TRANSACTION_TABLE).find(transaction).assign(remainingEdits).write();")
spec("B-R13", RD, "    {\n      receiverId: userId,\n      ...queryFields,\n    },\n", "")
spec("B-R14", RD, 'export const getTransactionsForUserContacts = (userId: string, query?: object) =>\n  uniqBy(\n    "id",\n    flatMap(\n      (contactId) => getTransactionsForUserForApi(contactId, query),\n      getContactIdsForUser(userId)\n    )\n  );', "export const getTransactionsForUserContacts = (userId: string, query?: object): TransactionResponseItem[] => [];")
spec("B-R15", RD, "    return filter(\n      (transaction: Transaction) =>\n        isWithinInterval(new Date(transaction.createdAt), {\n          start: new Date(dateRangeStart),\n          end: new Date(dateRangeEnd),\n        }),\n      transactions\n    );", "    return transactions;")
spec("B-R16", RD, "    return filter(\n      (transaction: Transaction) => inRange(amountMin, amountMax, transaction.amount),\n      transactions\n    );", "    return transactions;")
spec("B-R17", "src/utils/transactionUtils.ts", "  const offset = (page - 1) * limit;", "  const offset = 0;")
spec("B-R18", RD, "export const getLikesByTransactionId = (transactionId: string) => getLikesByObj({ transactionId });", "export const getLikesByTransactionId = (transactionId: string): Like[] => [];")
spec("B-R19", RD, "  const comment = {\n    id: shortid(),\n    uuid: v4(),\n    content,", '  const comment = {\n    id: shortid(),\n    uuid: v4(),\n    content: content + "_rq2",')
spec("B-R20", RD, "    createPaymentNotification(\n      transaction.receiverId,\n      transaction.id,\n      PaymentNotificationStatus.received\n    );", "    // RQ2: omit received-payment notification.")
spec("B-R21", RD, "    createLikeNotification(senderId, transactionId, like.id);\n    createLikeNotification(receiverId, transactionId, like.id);", "    createLikeNotification(senderId, transactionId, like.id);\n    // RQ2: omit receiver like notification.")
spec("B-R22", RD, "    createCommentNotification(senderId, transactionId, comment.id);\n    createCommentNotification(receiverId, transactionId, comment.id);", "    createCommentNotification(senderId, transactionId, comment.id);\n    // RQ2: omit receiver comment notification.")
spec("B-R23", RD, "flow(getNotificationsByObj, formatNotificationsForApiResponse)({ userId, isRead: false });", "flow(getNotificationsByObj, formatNotificationsForApiResponse)({ userId });")
spec("B-R24", RD, "  db.get(NOTIFICATION_TABLE).find(notification).assign(edits).write();", "  // RQ2: omit notification update.")

def run(args: list[str], **kwargs) -> None:
    subprocess.run(args, check=True, **kwargs)

def save_record(record: dict) -> None:
    dest = ROOT / "source-versions.jsonl"
    rows = [json.loads(x) for x in dest.read_text().splitlines()] if dest.exists() else []
    rows = [r for r in rows if (r["subject"], r["fault_id"]) != (record["subject"], record["fault_id"])]
    rows.append(record)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    tmp.replace(dest)

def pristine_source(subject: str) -> Path:
    """This directory is never used as a runtime checkout (even for normal tests)."""
    dest = ROOT / "subjects" / subject / "pristine"
    if dest.exists():
        return dest
    dest.mkdir(parents=True)
    if subject == "conduit":
        run(["tar", "-xzf", str(dest.parent / "pinned-source.tar.gz"), "-C", str(dest), "--strip-components=1"])
    else:
        archive = dest.parent / "pinned-source.tar"
        with archive.open("wb") as stream:
            run(["git", "-C", str(RWA_ORIGINAL), "archive", "bdf6169232b919d9618ec29032addbd865f986cd"], stdout=stream)
        run(["tar", "-xf", str(archive), "-C", str(dest)])
    return dest

def deploy(source: Path, fid: str, *, build: bool) -> tuple[Path, str]:
    image = NORMAL_IMAGE if fid == "normal" else f"uisemtest-rq2-{fid.lower()}:20260907"
    dest = ROOT / "deploy" / fid
    dest.mkdir(parents=True, exist_ok=True)
    # Only use image names unique to RQ2; no build setting during per-case supervise.
    compose = (REPO / "deploy/conduit/docker-compose.yml").read_text()
    compose = re.sub(r"^name: .*$", f"name: uisemtest-rq2-{fid.lower()}", compose, count=1, flags=re.M)
    compose = compose.replace("    build: .", f"    image: {image}")
    (dest / "docker-compose.yml").write_text(compose)
    shutil.copy2(REPO / "deploy/conduit/reset.sh", dest / "reset.sh")
    if build:
        log = ROOT / "builds" / f"{fid}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as stream:
            if fid == "normal":
                run(["docker", "build", "-t", image, "-f", str(REPO / "deploy/conduit/Dockerfile"), str(REPO / "deploy/conduit")], stdout=stream, stderr=subprocess.STDOUT)
            else:
                # Complete backend copy retains one exact source patch; frontend and
                # dependencies are inherited from the identical RQ2 normal image.
                dockerfile = f"FROM {NORMAL_IMAGE}\nCOPY backend /app/backend\n"
                (source / "Dockerfile.rq2").write_text(dockerfile)
                run(["docker", "build", "-t", image, "-f", str(source / "Dockerfile.rq2"), str(source)], stdout=stream, stderr=subprocess.STDOUT)
    return dest, image

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", default="all")
    p.add_argument("--no-build", action="store_true")
    args = p.parse_args()
    for subject in ("rwa", "conduit"):
        if args.only not in {"all", "normal", f"normal-{subject}"}:
            continue
        source = ROOT / "subjects" / subject / "normal"
        assert (source / "package.json").is_file(), source
        row = dict(fault_id="normal", subject=subject, status="included", reason="pinned pristine source", patch_ref=None, source_root=str(source))
        if subject == "rwa":
            deps = source / "node_modules"
            if not deps.exists():
                deps.symlink_to(RWA_ORIGINAL / "node_modules", target_is_directory=True)
        else:
            d, image = deploy(source, "normal", build=not args.no_build)
            row.update(deploy_root=str(d), image=image, build_status="not_run" if args.no_build else "passed")
        save_record(row)
        print(subject, "normal ready", flush=True)
    for fid, rel, old, new in SPECS:
        if args.only not in {"all", "sources", fid}:
            continue
        subject = "conduit" if fid.startswith(("B-C", "H-C")) else "rwa"
        baseline = pristine_source(subject)
        source = baseline.parent / fid
        original = (baseline / rel).read_text()
        assert original.count(old) == 1, (fid, "replacement match", original.count(old))
        changed = original.replace(old, new, 1)
        if fid in EXTRA:
            old2, new2 = EXTRA[fid]
            assert changed.count(old2) == 1
            changed = changed.replace(old2, new2, 1)
        shutil.copytree(baseline, source, symlinks=True, dirs_exist_ok=True)
        if subject == "rwa" and not (source / "node_modules").exists():
            (source / "node_modules").symlink_to(RWA_ORIGINAL / "node_modules", target_is_directory=True)
        (source / rel).write_text(changed)
        patch = ROOT / "patches" / f"{fid}.patch"
        patch.write_text("".join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True), fromfile=f"a/{rel}", tofile=f"b/{rel}")))
        row = dict(fault_id=fid, subject=subject, status="included", reason="single source fault from registered rule; activation not yet measured", patch_ref=str(patch), source_root=str(source), source_path=rel, build_status="not_run")
        row["candidate_tier"] = "conditional" if fid.startswith("H-") else "main"
        if fid in {"H-C01", "H-C03"}:
            row["condition_evidence"] = "Pinned User.email / Article.slug are DataTypes.STRING without unique/index constraints; index.js sync uses these models. Frozen mainchain includes L1-AUTH-02 / L1-ARTICLE-03 V6 rejection checks. No second constraint-removal fault is required."
        if subject == "conduit":
            run(["node", "--check", str(source / rel)])
            d, image = deploy(source, fid, build=not args.no_build)
            row.update(deploy_root=str(d), image=image, build_status="syntax_passed" if args.no_build else "passed")
        else:
            # TS parser is shared with the pinned app; no application import/start.
            checker = "const ts=require(process.argv[1]);const fs=require('fs');const p=process.argv[2];const r=ts.transpileModule(fs.readFileSync(p,'utf8'),{fileName:p,reportDiagnostics:true,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}});const e=(r.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error);if(e.length){console.error(e.map(x=>ts.flattenDiagnosticMessageText(x.messageText,' ')));process.exit(1)}"
            run(["node", "-e", checker, str(RWA_ORIGINAL / "node_modules/typescript"), str(source / rel)])
            row["build_status"] = "syntax_passed_runtime_compile_pending"
        save_record(row)
        print(fid, row["build_status"], flush=True)
    if args.only in {"all", "conditions"}:
        reasons = {
            "H-C02": "No frozen wrong-password rejection test: L1-AUTH-04 mainchain is empty; retained standalone auth test is login + protected_probe, not the specified negative-credential transition. Adding requests would change frozen inputs.",
            "H-C04": "L2-SETTINGS-02 mainchain is empty; standalone auth template contains login/protected_probe but no update-password + old/new-credential sequence. Original updateUser password OR guard also requires separate baseline behavior analysis; no fabricated equivalent claim.",
            "H-R01": "Frozen mainchain request coverage has zero POST /logout; retained auth templates contain login/protected_probe, not a logout transition. No existing unchanged protocol for the proposed omission is available.",
        }
        for fid, reason in reasons.items():
            save_record(dict(fault_id=fid, subject="rwa" if fid == "H-R01" else "conduit", status="conditional_unavailable", candidate_tier="conditional", reason=reason, patch_ref=None, source_root=None))
            print(fid, "conditional_unavailable", flush=True)

if __name__ == "__main__":
    main()

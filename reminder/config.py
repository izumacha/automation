"""タスク一覧と設定の永続化（JSON）。

タスクは ``~/.config/reminder/tasks.json`` に配列として保存される。
起床/就寝時刻や完了履歴などの設定は ``settings.json`` に保存される。
読み込み時に壊れたエントリは黙ってスキップし、アプリの起動を妨げない。
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .task import ISO_FMT, Task
from .timeline import DEFAULT_SLEEP_MIN, DEFAULT_WAKE_MIN, hhmm_to_min, min_to_hhmm

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "reminder")  # 設定ファイルを置くディレクトリのパスを組み立てる
_TASKS_PATH = os.path.join(_CONFIG_DIR, "tasks.json")  # タスク一覧を保存するJSONファイルのフルパスを定義する
_SETTINGS_PATH = os.path.join(_CONFIG_DIR, "settings.json")  # アプリ設定を保存するJSONファイルのフルパスを定義する
_CORRUPT_SUFFIX = ".corrupt"  # 読めないファイルを退避するときに元のパス末尾へ付ける拡張子
# 保存拒否中の変更内容を退避保存する復旧用ファイルの拡張子。復旧用ファイルは
# load_tasks / load_prefs から**決して自動読み込みしない**（本体ファイルが一時的に
# 読めなかっただけの可能性が高く、古い退避内容で健全なデータを黙って置き換える
# リスクを避けるため）。ユーザーが内容を確認して手動で復旧する前提の最小スコープとする。
_RECOVERY_SUFFIX = ".recovery"  # 復旧用ファイルを作るときに元のパス末尾へ付ける拡張子

# 完了履歴（Prefs.completions）を保持する日数の上限。統計（今日の完了数・連続達成日数）は
# 直近の連続した日しか参照しないため、2 年（730 日）残せば十分であり、無制限に伸び続ける
# リストによるファイル肥大・毎分の全履歴パース負荷を防ぐ（§8 一覧・リストの上限）。
COMPLETION_RETENTION_DAYS = 730  # 完了履歴を保持する日数（これより古いエントリは読み書き時に刈り込む）

# 設計判断: 一時的な I/O エラー（権限不足・ディスク障害などの OSError）で読み込めなかった
# ファイルのパスを記録しておく集合。壊れた JSON と違い、ファイル自体は健全なまま
# 「読めなかっただけ」の可能性が高いので、.corrupt への退避（改名）はしない。さらに、
# このセッション中に save_* が既定値ベースの内容でそのファイルを上書きすると、ディスク上の
# 健全なデータを丸ごと失ってしまうため、再び読み込みに成功するまで保存を拒否する
# （§9 fail-safe: 「読めなかったファイルには書かない」を安全側の既定とする）。
_failed_load_paths: set[str] = set()  # 読み込みに失敗した（保存を拒否すべき）ファイルパスの集合

# 保存拒否を UI 層へ知らせるためのコールバックの型。引数は
# (保存を拒否した本体ファイルのパス, 復旧用ファイルのパス（退避保存に失敗したら None）)。
SaveBlockedListener = Callable[[str, "str | None"], None]  # UI 通知コールバックの型エイリアス

# 設計判断: config.py は GUI 非依存の永続化層（§10 ロジックと UI の分離）なので、
# tkinter を import してダイアログを出すことはしない。代わりに「保存を拒否した」事実を
# コールバックで通知し、表示方法（ステータスバー・ダイアログ等）は登録側（app.py）に任せる。
_save_blocked_listener: SaveBlockedListener | None = None  # 保存拒否を通知する登録済みコールバック（未登録なら None）
_save_blocked_notified = False  # このセッションで保存拒否をすでに通知したかどうか（通知はセッション中 1 回だけ）


def set_save_blocked_listener(listener: SaveBlockedListener | None) -> None:
    """保存拒否（読み込み失敗による上書き停止）を通知するコールバックを登録する。

    listener には保存が拒否されたとき (本体ファイルのパス, 復旧用ファイルのパス or None)
    が渡される。None を渡すと登録を解除する。通知の連発を避けるため、コールバックの
    呼び出しはセッション中 1 回だけに制限され、新しい listener を登録し直すと
    「1 回だけ」のカウントもリセットされる（新しい利用者は改めて 1 回通知を受けられる）。
    """
    global _save_blocked_listener, _save_blocked_notified  # モジュール変数を書き換えるため global 宣言する
    _save_blocked_listener = listener  # 渡されたコールバック（または None）を登録する
    _save_blocked_notified = False  # 登録し直しに合わせて「通知済み」フラグをリセットする


def _now() -> datetime.datetime:
    """現在日時を返す。テスト時はこの関数をモックして時刻を固定できる。"""
    return datetime.datetime.now()  # システムの現在日時を取得して返す（app.py の _get_now と同じ分離パターン）


def _handle_refused_save(path: str, payload: object) -> None:
    """保存拒否時の後処理: 変更内容を復旧用ファイルへ退避保存し、UI 層へ 1 回だけ通知する。

    本体ファイル（読み込みに失敗した健全かもしれないファイル）には一切書かず、
    隣に ``path + ".recovery"`` を作って「その日の編集内容」を失わせない（§9 fail-safe）。
    退避保存には本体保存と同じ原子的書き込みヘルパーを使う。退避にも失敗した場合は
    警告ログを残し、通知には復旧用ファイル無し（None）として伝える。
    """
    global _save_blocked_notified  # 「通知済み」フラグを書き換えるため global 宣言する
    # 以下の 2 変数はどちらも同じ「復旧用ファイル」を指すが、役割と型が違うので分けている。
    # recovery_path: 書き込み先そのもの。必ず文字列で、退避に失敗しても変わらない（ログにも使う）。
    # notified_recovery_path: 通知側へ渡す値。退避に失敗したときだけ None（＝復旧用ファイル無し）へ切り替える。
    recovery_path = path + _RECOVERY_SUFFIX  # 退避先ファイルのパス（本体パス + .recovery）を組み立てる
    notified_recovery_path: str | None = recovery_path  # 通知側へ渡す復旧用ファイルのパス（退避に失敗したら後で None に切り替える）
    try:
        _atomic_write_json(recovery_path, payload)  # 本体と同じ原子的書き込みで変更内容を復旧用ファイルへ退避保存する
        logging.warning("保存できなかった内容を復旧用ファイルへ退避保存しました (%s)", recovery_path)  # 退避先の場所をログで案内する
    except Exception as e:  # 退避保存自体に失敗した場合（本体が読めない状況ではディスク側の異常が続いている可能性が高い）
        logging.warning("復旧用ファイルへの退避保存に失敗しました (%s): %s", recovery_path, e)  # 退避失敗も握り潰さずログに残す（§6）
        notified_recovery_path = None  # 通知側へ「復旧用ファイルは作れなかった」ことを伝えるため None にする
    if _save_blocked_notified or _save_blocked_listener is None:  # すでに通知済み、または通知先が未登録なら
        return  # 二重通知や無意味な呼び出しをせず処理を終える
    _save_blocked_notified = True  # このセッションでは通知済みであることを記録する（通知は 1 回だけ）
    try:
        _save_blocked_listener(path, notified_recovery_path)  # 登録済みコールバックに保存拒否と復旧用ファイルの場所（作れなければ None）を知らせる
    except Exception as e:  # 通知側（UI 層）の失敗で永続化層が巻き込まれないよう捕捉する（fail-safe）
        logging.warning("保存拒否の通知コールバックの実行に失敗しました: %s", e)  # 通知失敗も握り潰さずログに残す（§6）


def _prune_completions(completions: list[str], now: datetime.datetime) -> list[str]:
    """保持期間（COMPLETION_RETENTION_DAYS）より古い完了履歴を刈り込んだ新しいリストを返す。

    境界はカットオフ日時を**含む**（ちょうど 730 日前の完了は保持する）。日時として
    解釈できない文字列は、load_tasks の壊れたエントリスキップと同じ方針で捨てる
    （stats.py 側でもどのみち無視され、残しても二度と使われないため）。
    """
    cutoff = now - datetime.timedelta(days=COMPLETION_RETENTION_DAYS)  # 保持期間の下限日時（これ以降を残す）を計算する
    kept: list[str] = []  # 保持する完了履歴を蓄積するリストを初期化する
    dropped = 0  # 刈り込んだ（捨てた）エントリ数のカウンタを初期化する
    for item in completions:  # 完了履歴の各 ISO 文字列に対してループする
        try:
            dt = datetime.datetime.strptime(item, ISO_FMT)  # ISO 文字列を datetime オブジェクトに変換する
        except (TypeError, ValueError):  # 日時として解釈できない壊れた値の場合
            dropped += 1  # 捨てた件数を 1 増やす
            continue  # このエントリは保持せず次へ進む
        if dt >= cutoff:  # カットオフ日時以降（境界ちょうども含む）の完了なら
            kept.append(item)  # 保持リストに追加する
        else:  # 保持期間より古い完了なら
            dropped += 1  # 捨てた件数を 1 増やす
    if dropped:  # 1 件でも刈り込んだ場合は
        logging.debug("保持期間を過ぎた/解釈できない完了履歴を %d 件刈り込みました", dropped)  # 何件消えたかをデバッグログに残す（§6）
    return kept  # 刈り込み後の完了履歴リストを返す


def _preserve_corrupt_file(path: str) -> None:
    """読み込めないファイルを ``path + ".corrupt"`` へ退避（改名）して保全する。

    壊れた JSON を読み込めなかった場合、そのまま空データで起動すると次回の
    save_* が壊れたファイルを新しい内容で上書きし、ユーザーが手動で直せた
    はずのデータが完全に失われてしまう。それを防ぐため、フォールバック前に
    元ファイルを退避先へ改名して残す（§9 fail-safe）。

    方針: 退避先に前回の退避ファイルが残っている場合は**上書き**する
    （常に「最新の壊れたファイル」を 1 つだけ残すシンプルな運用。世代管理は
    しない）。退避自体に失敗してもアプリの起動は妨げず、警告ログだけ残して
    続行する。
    """
    backup_path = path + _CORRUPT_SUFFIX  # 退避先のパス（元のパス + ".corrupt"）を組み立てる
    try:
        os.replace(path, backup_path)  # 壊れたファイルを退避先へ改名して保全する（既存の退避ファイルがあれば上書き）
    except OSError as e:  # 改名に失敗した場合（権限不足・ファイルが既に無い等）
        logging.warning("壊れたファイルの退避に失敗しました (%s → %s): %s", path, backup_path, e)  # 退避失敗も握り潰さずログに残す（§6）
        return  # 退避できなくても読み込み処理自体は続行する（fail-safe）
    logging.warning("読み込めないファイルを %s へ退避しました。必要ならこのファイルから手動で復旧できます。", backup_path)  # 退避先の場所をユーザーへ知らせる


# ディレクトリ fsync の省略をこのセッションで既に警告したかどうか。省略は「電源断への
# 耐性が失われたまま誰も気づけない」状態なので、POSIX では 1 回だけ警告として知らせる
# （保存のたびに鳴らすとうるさいため、_save_blocked_notified と同じ「1 回だけ」方式にする）。
_dir_fsync_warned = False  # POSIX でのディレクトリ fsync 省略をすでに警告したか


def _report_dir_fsync_skipped(what: str, directory: str, error: OSError) -> None:
    """ディレクトリ fsync を省略した事実を、実行環境に応じた深刻度で記録する。

    Windows ではディレクトリを fsync できないが、os.replace（MoveFileEx）が
    メタデータを同期的に更新するため省略は**想定内**であり、デバッグログで十分。

    一方 POSIX で省略が起きるのは想定外（SELinux/AppArmor の拒否、FUSE 系ホーム、
    制限の強いコンテナのマウントなど）で、そのとき失われるのは
    まさに _fsync_directory が足そうとした電源断耐性そのものである。デバッグログに
    落とすと cli.py が INFO で起動する以上ユーザーには一生見えないため、警告として
    残す（§6 エラーを握り潰さない）。ただし保存のたびに鳴らさないよう 1 回だけにする。
    """
    global _dir_fsync_warned  # 「警告済み」フラグを書き換えるため global 宣言する
    if os.name == "posix" and not _dir_fsync_warned:  # POSIX で、まだ警告していない場合のみ
        _dir_fsync_warned = True  # このセッションでは警告済みであることを記録する（通知は 1 回だけ）
        logging.warning(
            "%s (%s): %s — 保存内容は書けていますが、電源断で直前の保存が失われる可能性があります。",
            what, directory, error,
        )  # 耐性が失われている事実と、データ自体は無事であることの両方を伝える
        return  # 警告を出したのでデバッグログは重ねない
    logging.debug("%s (%s): %s", what, directory, error)  # Windows（想定内）と 2 回目以降はデバッグログに留める


def _fsync_directory(directory: str) -> None:
    """ディレクトリ自身を fsync し、その中で行った改名（os.replace）を確定させる。

    ファイル本体を fsync しても、それは「ファイルの中身」がディスクへ届いた保証にすぎず、
    「どの名前がどの中身を指すか」（ディレクトリエントリ）はまだ OS のメモリ上にしか
    無いことがある。この状態で電源が落ちると、中身は無事なのに改名だけが失われ、
    本番ファイルが**改名前の古い内容へ巻き戻る**（一時ファイル名のまま残る場合もある）。
    ディレクトリを開いて fsync すると、この改名そのものがディスクへ確定する。

    移植性（§10）: ディレクトリを開いて fsync できるのは POSIX（Linux / macOS）だけで、
    Windows ではディレクトリを os.open できず PermissionError 等になる。ただし Windows の
    os.replace（MoveFileEx）はメタデータを同期的に更新するため、この処理は不要である。
    そのため失敗は「その環境では不要か、できないだけ」とみなし、記録を残して続行する。
    ここで書き込み自体を失敗扱いにすると、中身は正しく置き換わっているのに save_* が
    「保存に失敗」と誤報してしまう。記録の深刻度は環境によって変える
    （_report_dir_fsync_skipped の docstring を参照）。

    **この関数は例外を投げない。** 後始末の os.close も含めて捕捉する。呼び出し元
    （_atomic_write_json）はこの前提のうえで、改名成功後に無防備に呼んでいる。close は
    NFS / FUSE 上で遅延した I/O エラーを報告することがあり、これを外へ漏らすと
    「書き込みも改名も成功したのに保存失敗と誤報する」という、まさにこの関数が
    避けようとしている誤りが起きる。
    """
    try:
        fd = os.open(directory, os.O_RDONLY)  # ディレクトリ自身を読み取り専用で開いてファイルディスクリプタを得る
    except OSError as e:  # Windows など、ディレクトリを開けない環境の場合
        _report_dir_fsync_skipped("ディレクトリを開けないため fsync を省略しました", directory, e)  # 省略した理由を環境に応じた深刻度で記録する（§6）
        return  # 改名自体は完了しているので、確定できなくてもそのまま続行する
    try:
        os.fsync(fd)  # ディレクトリエントリ（名前→中身の対応）をディスクへ確定させる
    except OSError as e:  # ディレクトリの fsync に対応しないファイルシステムなどの場合
        _report_dir_fsync_skipped("ディレクトリの fsync に失敗しました", directory, e)  # 失敗理由を環境に応じた深刻度で記録する（§6）
    finally:
        try:
            os.close(fd)  # 例外の有無にかかわらずファイルディスクリプタを必ず閉じる（§8 リソースの解放）
        except OSError as e:  # close 自体が遅延 I/O エラーを報告した場合（NFS / FUSE で起こりうる）
            # ここで捕まえないと finally の例外がそのまま呼び出し元へ抜け、保存は成功して
            # いるのに save_* が「保存に失敗しました」と誤報する（docstring の「例外を投げない」も破れる）。
            logging.debug("ディレクトリのファイルディスクリプタを閉じられませんでした (%s): %s", directory, e)  # 後始末の失敗は致命的ではないのでデバッグログに留める（§6）


def _atomic_write_json(path: str, payload: object) -> None:
    """payload を JSON として path へ原子的（アトミック）に書き出す。

    まず同じディレクトリ内の一時ファイルへ全内容を書き、最後に os.replace で
    本番ファイルへ「一気に」差し替える。こうすると、書き込み途中でクラッシュ・
    電源断・例外が起きても本番ファイルは壊れない。本番パスを直接 "w" で開くと
    開いた瞬間に中身が空に切り詰められ、途中で失敗するとユーザーの全タスク／
    設定を丸ごと失う恐れがあるため、その事故を防ぐのが狙い（§9 fail-safe）。

    一時ファイルを同一ディレクトリに作るのは、os.replace が同じファイルシステム
    上でのみ原子的に働くため。os.replace は POSIX / Windows どちらでも原子的に
    置き換わる（§10 移植性）。失敗時は一時ファイルを後始末し、例外を呼び出し元へ
    再送出して save_* 側でログに残せるようにする。

    電源断への耐性には fsync が 2 段階必要である。中身の fsync（下の os.fsync）だけでは
    「新しい中身」しか確定せず、それを本番の名前へ結び付けた改名は確定しないため、
    最後に _fsync_directory でディレクトリエントリも確定させる（詳細は同関数の docstring）。
    """
    directory = os.path.dirname(path) or "."  # 一時ファイルを本番ファイルと同じディレクトリに作るため親ディレクトリを取り出す（空なら現在地）
    os.makedirs(directory, exist_ok=True)  # 保存先ディレクトリが存在しない場合は作成する
    # delete=False ではなく mkstemp を使い、書き込み後に os.replace で本番へ差し替える
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")  # 同一ディレクトリ上に一時ファイルを作成しFDを得る
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:  # 低レベルFDをUTF-8テキストファイルとして開く（with終了時にcloseされる）
            json.dump(payload, f, ensure_ascii=False, indent=2)  # ペイロードをインデント付きJSONとして一時ファイルへ書き出す
            f.flush()  # PythonのバッファをOSへ確実に渡す
            os.fsync(f.fileno())  # OSバッファをディスクへ同期し、置き換え後に中身が空になる事故を防ぐ
        os.replace(tmp_path, path)  # 一時ファイルを本番ファイルへ原子的に差し替える（成功時は一時ファイルは消える）
    except Exception:  # 書き込みまたは置き換えに失敗した場合
        try:
            os.unlink(tmp_path)  # 書きかけの一時ファイルを削除して後始末する（本番ファイルは無傷のまま）
        except OSError as e:  # 一時ファイルが既に無い等で削除に失敗しても
            # 後始末の失敗は致命的ではないため無視する。
            logging.debug("一時ファイルの後始末に失敗しました (%s): %s", tmp_path, e)  # 想定内の良性エラーなのでデバッグログにだけ原因を残す（§6: エラーを握り潰さない）
        raise  # 元の例外を呼び出し元へ再送出し、save_* 側で警告ログに残せるようにする
    # ここへ来るのは os.replace が成功したときだけ（失敗時は上の except で再送出済み）。
    # 改名をディスクへ確定させる。_fsync_directory は例外を投げない（＝保存の成否を変えない）。
    _fsync_directory(directory)  # ディレクトリエントリを fsync し、電源断で改名が巻き戻るのを防ぐ


@dataclass
class Prefs:
    """永続化するアプリ設定。

    Attributes:
        wake: 起床時刻（"HH:MM"）。タイムラインの開始境界。
        sleep: 就寝時刻（"HH:MM"）。タイムラインの終了境界。
        completions: 完了日時（ISO 文字列）の履歴。統計に使用する。
    """

    wake: str = field(default_factory=lambda: min_to_hhmm(DEFAULT_WAKE_MIN))  # 起床時刻のデフォルト値をデフォルト起床分から生成する
    sleep: str = field(default_factory=lambda: min_to_hhmm(DEFAULT_SLEEP_MIN))  # 就寝時刻のデフォルト値をデフォルト就寝分から生成する
    completions: list[str] = field(default_factory=list)  # 完了履歴リストを空リストで初期化する


def load_prefs() -> Prefs:
    """設定を読み込む。存在しない/壊れている場合は既定値を返す。"""
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:  # 設定ファイルを UTF-8 で開く
            data = json.load(f)  # JSON として読み込んで辞書に変換する
    except FileNotFoundError:  # ファイルが存在しない場合
        return Prefs()  # デフォルト設定を返す
    except (ValueError, UnicodeDecodeError, RecursionError) as e:  # 中身が JSON / UTF-8 として解釈できない・異常に深いネストで解析不能な場合（本当に壊れたファイル）。JSONDecodeError は ValueError のサブクラスで、json.load は桁数上限（int_max_str_digits）超過の巨大整数などで素の ValueError も投げるため、親クラスで両方を捕捉する
        logging.warning("設定ファイルの読み込みに失敗しました (%s): %s", _SETTINGS_PATH, e)  # 失敗したパスと原因例外の両方を残す（§6: 例外を握り潰さない）
        _preserve_corrupt_file(_SETTINGS_PATH)  # 壊れた設定ファイルを退避し、次回 save_prefs での上書き消失を防ぐ
        return Prefs()  # デフォルト設定を返す
    except OSError as e:  # 権限不足・ディスク障害などの一時的な I/O エラーで開けなかった/読めなかった場合
        # ファイルの中身は健全なまま読めなかっただけの可能性が高いので、退避（改名）せず
        # そのまま残し、このセッション中の save_prefs による上書きも拒否する（_failed_load_paths のコメント参照）
        logging.warning("設定ファイルを一時的なI/Oエラーで読み込めませんでした (%s): %s", _SETTINGS_PATH, e)  # 隔離せずに済ませた理由が追えるよう原因を残す（§6）
        _failed_load_paths.add(_SETTINGS_PATH)  # 保存拒否の対象としてこのパスを記録する（fail-safe）
        return Prefs()  # ファイルには一切手を付けず、デフォルト設定で継続する
    _failed_load_paths.discard(_SETTINGS_PATH)  # 読み込みに成功したので、このパスへの保存拒否を解除する

    if not isinstance(data, dict):  # 読み込んだデータが辞書でない場合（不正な形式）
        logging.warning("設定ファイルの形式が不正です (%s): 辞書形式ではありません", _SETTINGS_PATH)  # 形式不正も黙って捨てずログに残す（§6）
        _preserve_corrupt_file(_SETTINGS_PATH)  # 形式不正のファイルも同様に退避してから既定値へフォールバックする
        return Prefs()  # デフォルト設定を返す

    prefs = Prefs(**{k: v for k, v in data.items() if k in Prefs.__dataclass_fields__})  # 既知のフィールドだけを使って Prefs を生成する
    # completions は文字列リストであることを保証する（壊れた値は捨てる）
    if not isinstance(prefs.completions, list):  # completions がリストでない場合（不正な型）
        prefs.completions = []  # 空リストにリセットして不正な値を捨てる
    else:
        prefs.completions = [c for c in prefs.completions if isinstance(c, str)]  # 文字列でない要素を除去して文字列リストだけ保持する
    prefs.completions = _prune_completions(prefs.completions, _now())  # 保持期間を過ぎた古い完了履歴を刈り込み、無制限に増えないようにする（§8）
    # /code-review ultra 指摘対応: wake/sleep は completions と異なり検証されておらず、
    # 不正値（数値・null・範囲外の "HH:MM" 等）が settings.json に混入すると、
    # PlannerApp._wake_min()/_sleep_min() 側の例外処理で毎回デフォルトへ黙って
    # フォールバックし続け（ログに残らない）、しかも save_prefs() のたびに壊れた
    # 値がそのまま書き戻され続けてしまう。他のフォールバックと同じく警告ログを
    # 残した上で、ここで一度だけ正規の "HH:MM" 文字列に正規化する
    prefs.wake = _coerce_hhmm(prefs.wake, DEFAULT_WAKE_MIN, "wake")  # 起床時刻を検証し、不正なら既定値へ正規化する
    prefs.sleep = _coerce_hhmm(prefs.sleep, DEFAULT_SLEEP_MIN, "sleep")  # 就寝時刻を検証し、不正なら既定値へ正規化する
    return prefs  # 正常に読み込んだ設定を返す


def _coerce_hhmm(value: object, default_minutes: int, field_name: str) -> str:
    """設定値を "HH:MM" 形式の文字列として検証し、不正なら警告ログを残して既定値へ正規化する。"""
    if isinstance(value, str):  # 文字列型であれば形式・範囲の検証を試みる
        try:
            hhmm_to_min(value)  # "HH:MM" として解釈できるか（0〜23時・0〜59分か）を検証する
            return value  # 検証を通過した値はそのまま採用する
        except ValueError:
            pass  # 形式・範囲が不正な場合は下の警告ログ＋既定値フォールバックへ進む
    # 文字列以外の型（数値・null・リスト等）、または "HH:MM" として解釈できない文字列
    logging.warning(
        "設定ファイルの %s が不正なため既定値を使用します (%s): %r", field_name, _SETTINGS_PATH, value
    )  # 他のフォールバックと同じく、警告ログに壊れた値を残す（§6: 例外を握り潰さない）
    return min_to_hhmm(default_minutes)  # 既定値を "HH:MM" 文字列に整形して返す


def save_prefs(prefs: Prefs) -> None:
    """設定を JSON ファイルに原子的に書き出す（途中失敗で既存設定を壊さない）。

    書き出す前に完了履歴（completions）を保持期間で刈り込む。刈り込み結果は
    prefs.completions にも書き戻し、ファイルだけでなくメモリ上の履歴（stats.py が
    毎分パースするリスト）も上限内に保つ（§8）。
    """
    prefs.completions = _prune_completions(prefs.completions, _now())  # 保存のたびに古い完了履歴を刈り込み、ファイルとメモリの肥大化を防ぐ
    payload = asdict(prefs)  # 保存する内容（辞書）をここで確定させる（通常保存と退避保存で同じ内容を使うため）
    if _SETTINGS_PATH in _failed_load_paths:  # このセッション中に一時的な I/O エラーで読み込めなかったファイルの場合
        logging.warning("設定ファイルは読み込みに失敗しているため、上書き保存を中止しました (%s)", _SETTINGS_PATH)  # 保存を拒否したことを黙って捨てずログに残す（§6）
        # tasks.json と保存拒否の構造が完全に対称（payload を差し替えるだけ）なので、
        # 復旧用ファイルへの退避保存と UI 通知も同じヘルパーで settings.json にも適用する。
        _handle_refused_save(_SETTINGS_PATH, payload)  # 変更内容を settings.json.recovery へ退避保存し、UI 層へ 1 回だけ通知する
        return  # ディスク上の健全なデータを既定値ベースの内容で潰さないよう保存しない（fail-safe）
    try:
        _atomic_write_json(_SETTINGS_PATH, payload)  # 一時ファイル経由で安全に設定を書き出す
    except Exception as e:  # ファイル書き込みで何らかのエラーが発生した場合
        logging.warning("設定ファイルの保存に失敗しました (%s): %s", _SETTINGS_PATH, e)  # 失敗したパスと原因例外の両方を残す（§6: 例外を握り潰さない）


def load_tasks() -> list[Task]:
    """タスク一覧を読み込む。ファイルが無い/壊れている場合は空リストを返す。"""
    try:
        with open(_TASKS_PATH, encoding="utf-8") as f:  # タスクファイルを UTF-8 で開く
            data = json.load(f)  # JSON として読み込んでリストに変換する
    except FileNotFoundError:  # ファイルが存在しない場合（初回起動など）
        return []  # タスクが存在しないとして空リストを返す
    except (ValueError, UnicodeDecodeError, RecursionError) as e:  # 中身が JSON / UTF-8 として解釈できない・異常に深いネストで解析不能な場合（本当に壊れたファイル）。JSONDecodeError は ValueError のサブクラスで、json.load は桁数上限（int_max_str_digits）超過の巨大整数などで素の ValueError も投げるため、親クラスで両方を捕捉する
        logging.warning("タスクファイルの読み込みに失敗しました (%s): %s", _TASKS_PATH, e)  # 失敗したパスと原因例外の両方を残す（§6: 例外を握り潰さない）
        _preserve_corrupt_file(_TASKS_PATH)  # 壊れたタスクファイルを退避し、次回 save_tasks での上書き消失を防ぐ
        return []  # 読み込み失敗なので空リストを返す
    except OSError as e:  # 権限不足・ディスク障害などの一時的な I/O エラーで開けなかった/読めなかった場合
        # ファイルの中身は健全なまま読めなかっただけの可能性が高いので、退避（改名）せず
        # そのまま残し、このセッション中の save_tasks による上書きも拒否する（_failed_load_paths のコメント参照）
        logging.warning("タスクファイルを一時的なI/Oエラーで読み込めませんでした (%s): %s", _TASKS_PATH, e)  # 隔離せずに済ませた理由が追えるよう原因を残す（§6）
        _failed_load_paths.add(_TASKS_PATH)  # 保存拒否の対象としてこのパスを記録する（fail-safe）
        return []  # ファイルには一切手を付けず、空リストで継続する
    _failed_load_paths.discard(_TASKS_PATH)  # 読み込みに成功したので、このパスへの保存拒否を解除する

    if not isinstance(data, list):  # 読み込んだデータがリストでない場合（不正な形式）
        logging.warning("タスクファイルの形式が不正です (%s): リスト形式ではありません", _TASKS_PATH)  # 形式不正も黙って捨てずログに残す（§6）
        _preserve_corrupt_file(_TASKS_PATH)  # 形式不正のファイルも同様に退避してから空リストへフォールバックする
        return []  # 空リストを返して不正なデータを無視する

    tasks: list[Task] = []  # 読み込んだタスクを蓄積するリストを初期化する
    seen_ids: set[str] = set()  # 重複IDを検出するためにすでに見たIDを記録するセットを初期化する
    # スキップは「静かな永久欠損」になり得る（読み込まれなかったエントリは次回 save_tasks で
    # ファイルから消える）ため、debug ではなく warning で残す。アプリは INFO レベルで起動する
    # （cli.py の basicConfig）ので、debug ではユーザーに一切見えないまま消えてしまう。
    # ログにはエントリ全文ではなく「何件目か＋タイトル」だけを載せる（長大な本文でログを埋めない）。
    for index, entry in enumerate(data):  # JSONから読み込んだ各エントリに対して、位置（何件目か）付きでループする
        if not isinstance(entry, dict):  # エントリが辞書でない場合（不正な要素）
            logging.warning("壊れたタスクエントリをスキップしました (%d件目): 辞書形式ではありません", index + 1)  # 何件目が捨てられたかを警告ログで知らせる
            continue  # そのエントリをスキップして次へ進む
        try:
            task = Task.from_dict(entry)  # 辞書からTaskオブジェクトを生成する
        except Exception as e:  # 1 件壊れていても残りは読み込めるよう、個別にスキップする
            logging.warning(
                "壊れたタスクエントリをスキップしました (%d件目, title=%r): %s", index + 1, entry.get("title"), e
            )  # どのエントリが捨てられたか（位置とタイトル）と原因例外を警告ログで知らせる
            continue  # このエントリをスキップして次のエントリへ進む
        # Treeview の iid には task.id を使うため「空でない一意な文字列」でなければならない。
        # 手編集や不正なマージで id が空文字・非文字列（例: 123）・重複になっていると、
        # 空文字は Treeview のルート item と衝突し、非文字列は選択時に文字列化されて
        # PlannerApp._selected()（_find() 経由の照合）がマッチできない。これらの場合は再採番して起動不能を防ぐ。
        if not isinstance(task.id, str) or not task.id or task.id in seen_ids:  # IDが不正（非文字列・空・重複）な場合
            task.id = uuid.uuid4().hex  # ランダムな一意IDを新たに割り当てる
        seen_ids.add(task.id)  # このIDを「使用済み」として記録する
        tasks.append(task)  # 正常なタスクをリストに追加する
    return tasks  # 読み込んだタスクのリストを返す


def save_tasks(tasks: list[Task]) -> None:
    """タスク一覧を JSON ファイルに原子的に書き出す（途中失敗で既存タスクを壊さない）。"""
    payload = [t.to_dict() for t in tasks]  # 保存する内容（辞書のリスト）をここで確定させる（通常保存と退避保存で同じ内容を使うため）
    if _TASKS_PATH in _failed_load_paths:  # このセッション中に一時的な I/O エラーで読み込めなかったファイルの場合
        logging.warning("タスクファイルは読み込みに失敗しているため、上書き保存を中止しました (%s)", _TASKS_PATH)  # 保存を拒否したことを黙って捨てずログに残す（§6）
        _handle_refused_save(_TASKS_PATH, payload)  # その日の編集内容を tasks.json.recovery へ退避保存し、UI 層へ 1 回だけ通知する
        return  # ディスク上の健全なデータを既定値ベースの内容で潰さないよう保存しない（fail-safe）
    try:
        _atomic_write_json(_TASKS_PATH, payload)  # 一時ファイル経由で安全にタスク一覧を書き出す
    except Exception as e:  # ファイル書き込みで何らかのエラーが発生した場合
        logging.warning("タスクファイルの保存に失敗しました (%s): %s", _TASKS_PATH, e)  # 失敗したパスと原因例外の両方を残す（§6: 例外を握り潰さない）

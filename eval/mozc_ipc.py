#!/usr/bin/env python3
"""稼働中の mozc_server と名前付きパイプで直接会話するクライアント（Windows専用）。

Mozc の IPC はメッセージモードの名前付きパイプで、長さ接頭辞もハンドシェイクも
無い。`commands.proto` の **Input** を1メッセージ書くと **Output** が1メッセージ
返る。`Command` ではなく `Input` を送る点に注意（session_server.cc が
`command.mutable_input()->ParseFromArray(...)` で受けている）。

前提:
    python eval/fetch_mozc_protos.py   を先に実行して protobuf を生成しておくこと。

辞書のON/OFF:
    `user_dictionary_disabled()` は user_dictionary.db を空の辞書へ差し替え、
    RELOAD_AND_WAIT を送る。**ファイルを削除するだけでは切り替わらない**
    （読み込みに失敗した Mozc は既存のデータを保持するため）。
    元のファイルは必ず復元される。
"""
import contextlib
import ctypes
import os
import shutil
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO_DIR = os.path.join(HERE, "_mozc_proto")

if PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)

try:
    from protocol import commands_pb2
    from protocol import user_dictionary_storage_pb2
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "protobuf が生成されていません。先に次を実行してください:\n"
        "    python eval/fetch_mozc_protos.py\n"
        f"（{e}）")

PIPE_PREFIX = "\\\\.\\pipe\\"
_DEFAULT_PROFILE = os.path.join(
    os.environ.get("USERPROFILE", ""), "AppData", "LocalLow", "Mozc")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
PIPE_READMODE_MESSAGE = 0x00000002
ERROR_PIPE_BUSY = 231
_INVALID_HANDLE = ctypes.c_void_p(-1).value

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                             wintypes.HANDLE]
_k32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
_k32.WaitNamedPipeW.restype = wintypes.BOOL


def find_session_pipe():
    """mozc_server のセッション用パイプ名を返す。見つからなければ None。"""
    try:
        names = os.listdir(PIPE_PREFIX)
    except OSError:
        return None
    for name in names:
        if name.startswith("mozc.") and name.endswith(".session"):
            return PIPE_PREFIX + name
    return None


def user_dictionary_path():
    """user_dictionary.db の既定の場所。Windows では LocalLow にある。"""
    return os.path.join(_DEFAULT_PROFILE, "user_dictionary.db")


class MozcError(RuntimeError):
    pass


class MozcClient:
    """1リクエスト1接続。Mozc の IPC サーバはそういう作りになっている。"""

    def __init__(self, pipe=None, read_buffer=1 << 21, retries=40):
        self.pipe = pipe or find_session_pipe()
        if not self.pipe:
            raise MozcError("mozc_server のパイプが見つかりません。起動していますか？")
        self._buf_size = read_buffer
        self._retries = retries

    def _open(self):
        """パイプを開く。サーバは1接続ずつしか捌かないので BUSY を待って再試行する。"""
        last_error = 0
        for _ in range(self._retries):
            handle = _k32.CreateFileW(self.pipe, GENERIC_READ | GENERIC_WRITE, 0,
                                      None, OPEN_EXISTING, 0, None)
            if handle != _INVALID_HANDLE and handle is not None:
                return handle
            last_error = ctypes.get_last_error()
            if last_error != ERROR_PIPE_BUSY:
                break
            # 本家クライアント (win32_ipc.cc) と同じく空きを待つ
            _k32.WaitNamedPipeW(self.pipe, 5000)
        raise MozcError(f"接続に失敗しました (error {last_error})")

    def call(self, request):
        payload = request.SerializeToString()
        handle = self._open()
        try:
            mode = wintypes.DWORD(PIPE_READMODE_MESSAGE)
            _k32.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None)

            written = wintypes.DWORD()
            if not _k32.WriteFile(handle, payload, len(payload),
                                  ctypes.byref(written), None):
                raise MozcError(f"送信に失敗しました (error {ctypes.get_last_error()})")

            buf = ctypes.create_string_buffer(self._buf_size)
            read = wintypes.DWORD()
            ok = _k32.ReadFile(handle, buf, self._buf_size, ctypes.byref(read), None)
            if not ok and read.value == 0:
                # サーバは応答が空のとき、送らずに切断する（win32_ipc.cc の Loop）
                raise MozcError(f"応答がありません (error {ctypes.get_last_error()})")
        finally:
            _k32.CloseHandle(handle)

        output = commands_pb2.Output()
        output.ParseFromString(buf.raw[:read.value])
        return output

    def server_version(self):
        out = self.call(commands_pb2.Input(type=commands_pb2.Input.GET_SERVER_VERSION))
        return out.server_version.mozc_version if out.HasField("server_version") else ""

    def reload(self, wait=3.0):
        """ユーザー辞書を再読み込みさせる。反映は非同期なので少し待つ。"""
        self.call(commands_pb2.Input(type=commands_pb2.Input.RELOAD_AND_WAIT))
        time.sleep(wait)

    @contextlib.contextmanager
    def _session(self):
        sid = self.call(commands_pb2.Input(
            type=commands_pb2.Input.CREATE_SESSION)).id
        try:
            req = commands_pb2.Input(type=commands_pb2.Input.SEND_COMMAND, id=sid)
            req.command.type = commands_pb2.SessionCommand.SWITCH_COMPOSITION_MODE
            req.command.composition_mode = commands_pb2.HIRAGANA
            self.call(req)
            yield sid
        finally:
            self.call(commands_pb2.Input(
                type=commands_pb2.Input.DELETE_SESSION, id=sid))

    def convert(self, reading, limit=20):
        """ひらがなの読みを変換し、(第1候補, 候補リスト) を返す。

        読みは key_string として1文字ずつ送るため、ローマ字テーブルを経由しない。
        """
        with self._session() as sid:
            for ch in reading:
                req = commands_pb2.Input(type=commands_pb2.Input.SEND_KEY, id=sid)
                req.key.key_string = ch
                self.call(req)
            req = commands_pb2.Input(type=commands_pb2.Input.SEND_KEY, id=sid)
            req.key.special_key = commands_pb2.KeyEvent.SPACE
            out = self.call(req)

        top = ("".join(s.value for s in out.preedit.segment)
               if out.HasField("preedit") else "")
        cands = ([c.value for c in out.all_candidate_words.candidates[:limit]]
                 if out.HasField("all_candidate_words") else [])
        return top, cands


def _make_empty_storage(template_bytes):
    """既存の辞書と同じ id/name を持つ、エントリ0件のストレージを作る。"""
    src = user_dictionary_storage_pb2.UserDictionaryStorage()
    src.ParseFromString(template_bytes)
    empty = user_dictionary_storage_pb2.UserDictionaryStorage()
    if src.HasField("version"):
        empty.version = src.version
    for d in src.dictionaries:
        nd = empty.dictionaries.add()
        nd.id = d.id
        nd.name = d.name
    return empty.SerializeToString()


@contextlib.contextmanager
def user_dictionary_disabled(client, db_path=None, backup_path=None, wait=3.0):
    """ユーザー辞書を一時的に空にする。抜けるときに必ず元へ戻す。

    多重実行は禁止する。既に空へ差し替えられている状態で別のプロセスが
    同じことをすると、「空の辞書」をバックアップして復元してしまい、
    利用者の辞書が失われる。ロックファイルでこれを防ぐ。
    """
    db_path = db_path or user_dictionary_path()
    if not os.path.exists(db_path):
        raise MozcError(f"user_dictionary.db が見つかりません: {db_path}")

    lock_path = db_path + ".ablock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise MozcError(
            f"辞書の差し替えが既に実行中です: {lock_path} / "
            "他の測定スクリプトの終了を待ってください。"
            "異常終了した場合はこのファイルを削除してください。") from None
    os.write(lock_fd, str(os.getpid()).encode())
    os.close(lock_fd)

    backup_path = backup_path or (db_path + ".abbackup")
    original = open(db_path, "rb").read()
    with open(backup_path, "wb") as f:
        f.write(original)
    if os.path.getsize(backup_path) != len(original):
        raise MozcError("バックアップの検証に失敗しました。中止します。")

    try:
        with open(db_path, "wb") as f:
            f.write(_make_empty_storage(original))
        client.reload(wait)
        yield
    finally:
        try:
            with open(db_path, "wb") as f:
                f.write(original)
            client.reload(wait)
            if os.path.getsize(db_path) != len(original):
                raise MozcError(
                    f"辞書の復元に失敗しました。手動で戻してください: {backup_path}")
            os.remove(backup_path)
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)

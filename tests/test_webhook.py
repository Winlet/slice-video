import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from xmlslice.webhook import PATH, RECORDER_PATH, WebhookError, make_handler, parse_event


class ParseEventTests(unittest.TestCase):
    def test_file_closed_uses_danmu_path(self):
        job = parse_event(_payload(danmuPath="/tmp/a.xml"))
        self.assertEqual(job, ("/tmp/a.mp4", "/tmp/a.xml"))

    def test_file_closed_falls_back_to_sibling_xml(self):
        job = parse_event(_payload(danmuPath=""))
        self.assertEqual(job, ("/tmp/a.mp4", "/tmp/a.xml"))

    def test_other_events_are_ignored(self):
        self.assertIsNone(parse_event(_payload(event="FileOpening")))
        self.assertIsNone(parse_event(_payload(event="FileError")))

    def test_accepts_numeric_room_id_text(self):
        job = parse_event(_payload(roomId="93589"))
        self.assertEqual(job, ("/tmp/a.mp4", "/tmp/a.xml"))

    def test_recorder_file_closed_uses_record_dir(self):
        job = parse_event(
            {
                "EventType": "FileClosed",
                "EventTimestamp": "2021-05-14T17:52:54.9461101+08:00",
                "EventId": "98f85267-e08c-4f15-ad9a-1fc463d42b0b",
                "EventData": {
                    "RelativePath": "23058-房间/录制.flv",
                    "RoomId": 23058,
                    "Name": "主播",
                    "Title": "标题",
                },
            },
            record_dir="/records",
        )
        self.assertEqual(job, ("/records/23058-房间/录制.flv", "/records/23058-房间/录制.xml"))

    def test_recorder_other_events_are_ignored(self):
        self.assertIsNone(parse_event({"EventType": "FileOpening", "EventData": {}}))

    def test_wrapped_file_closed(self):
        job = parse_event(
            {
                "id": "1",
                "version": 1,
                "time": "2021-05-14T17:52:54.946",
                "type": "FileClosed",
                "data": {"filePath": "/tmp/a.mp4", "roomId": 93589},
            }
        )
        self.assertEqual(job, ("/tmp/a.mp4", "/tmp/a.xml"))

    def test_wrapped_transmux_uses_output(self):
        job = parse_event(
            {
                "id": "1",
                "version": "1",
                "time": "2026-03-11T05:22:38Z",
                "type": "video_transmux_finish",
                "data": {"output": "/tmp/out.mp4", "input": "/tmp/in.ts", "channel": "1"},
            }
        )
        self.assertEqual(job, ("/tmp/out.mp4", "/tmp/out.xml"))

    def test_wrapped_blrec_completed(self):
        job = parse_event(
            {
                "id": "1",
                "date": "2021-05-14T17:52:54+08:00",
                "type": "VideoFileCompletedEvent",
                "data": {"room_id": 1, "path": "/tmp/a.flv"},
            }
        )
        self.assertEqual(job, ("/tmp/a.flv", "/tmp/a.xml"))

    def test_wrapped_file_create_is_ignored(self):
        self.assertIsNone(
            parse_event(
                {
                    "id": "1",
                    "version": 1,
                    "time": "2026-03-11T05:22:38Z",
                    "type": "video_file_create",
                    "data": {"path": "/tmp/a.ts"},
                }
            )
        )

    def test_missing_field(self):
        payload = _payload()
        del payload["filePath"]
        with self.assertRaises(WebhookError) as caught:
            parse_event(payload)
        self.assertEqual(caught.exception.status, 400)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.jobs = []
        sliced = threading.Event()
        forwarded = threading.Event()

        def slice_job(video, xml_path):
            self.jobs.append((video, xml_path))
            sliced.set()

        self.sliced = sliced
        self.forwarded_event = forwarded
        self.forwarded = []

        def forward(raw):
            self.forwarded.append(raw)
            forwarded.set()

        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(slice_job, forward, record_dir="/records"),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}{PATH}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def test_file_closed_starts_slice(self):
        status, body = _post(self.url, _payload())
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})
        self.assertTrue(self.sliced.wait(2))
        self.assertTrue(self.forwarded_event.wait(2))
        self.assertEqual(self.jobs, [("/tmp/a.mp4", "/tmp/a.xml")])
        self.assertEqual(json.loads(self.forwarded[0]), _payload())

    def test_recorder_file_closed_starts_slice(self):
        url = f"http://127.0.0.1:{self.server.server_address[1]}{RECORDER_PATH}"
        status, body = _post(
            url,
            {
                "EventType": "FileClosed",
                "EventData": {"RelativePath": "房间/录制.mp4", "RoomId": 1},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})
        self.assertTrue(self.sliced.wait(2))
        self.assertEqual(self.jobs, [("/records/房间/录制.mp4", "/records/房间/录制.xml")])

    def test_bad_json(self):
        request = urllib.request.Request(
            self.url,
            data=b"not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 400)


def _payload(**overrides):
    payload = {
        "event": "FileClosed",
        "filePath": "/tmp/a.mp4",
        "coverPath": "",
        "danmuPath": "",
        "roomId": 123,
        "time": "2021-05-14T17:52:54.946",
        "title": "标题",
        "username": "主播",
        "platform": "custom",
        "software": "custom",
    }
    payload.update(overrides)
    return payload


def _post(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

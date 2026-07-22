from __future__ import annotations

import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from echobot.attachments import AttachmentStore, FileBudget
from echobot.images import ImageBudget, image_bytes_to_jpeg_data_url, normalize_image_bytes


def make_png_bytes(*, size: tuple[int, int] = (2, 2)) -> bytes:
    image = Image.new("RGBA", size, (255, 0, 0, 128))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ImageNormalizationTests(unittest.TestCase):
    def test_normalize_image_bytes_returns_jpeg_bytes(self) -> None:
        normalized = normalize_image_bytes(make_png_bytes())

        self.assertEqual("image/jpeg", normalized.content_type)

        with Image.open(BytesIO(normalized.image_bytes)) as image:
            self.assertEqual("JPEG", image.format)
            self.assertEqual("RGB", image.mode)
            self.assertEqual((2, 2), image.size)

    def test_image_bytes_to_jpeg_data_url_returns_jpeg_data_url(self) -> None:
        jpeg_data_url = image_bytes_to_jpeg_data_url(make_png_bytes(size=(3, 1)))

        self.assertTrue(jpeg_data_url.startswith("data:image/jpeg;base64,"))

        encoded_bytes = jpeg_data_url.split(",", 1)[1]
        jpeg_bytes = base64.b64decode(encoded_bytes)
        with Image.open(BytesIO(jpeg_bytes)) as image:
            self.assertEqual("JPEG", image.format)
            self.assertEqual((3, 1), image.size)

    def test_normalize_image_bytes_respects_output_budget(self) -> None:
        normalized = normalize_image_bytes(
            make_png_bytes(size=(512, 512)),
            budget=ImageBudget(max_output_bytes=20_000, max_side=256),
        )

        self.assertLessEqual(len(normalized.image_bytes), 20_000)
        self.assertLessEqual(max(normalized.width, normalized.height), 256)


class AttachmentStoreTests(unittest.TestCase):
    def test_file_attachment_is_materialized_inside_tool_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_store = AttachmentStore(root / "private-store" / "attachments")
            tool_workspace = root / "tenant-workspace"
            attachment = attachment_store.create_file_attachment(
                b"original attachment",
                content_type="text/plain",
                filename="notes.txt",
            )

            content = attachment_store.file_attachment_message_content(
                attachment.attachment_id,
                workspace=tool_workspace,
            )

            materialized_path = tool_workspace / content["workspace_path"]
            self.assertTrue(materialized_path.is_file())
            self.assertEqual(b"original attachment", materialized_path.read_bytes())

            materialized_path.write_bytes(b"tool-local mutation")
            self.assertEqual(
                b"original attachment",
                attachment_store.file_attachment_path(
                    attachment.attachment_id
                ).read_bytes(),
            )

    def test_file_attachment_metadata_cannot_escape_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_store = AttachmentStore(root / "attachments")
            attachment = attachment_store.create_file_attachment(
                b"inside",
                filename="notes.txt",
            )
            outside_path = root / "outside.txt"
            outside_path.write_text("outside", encoding="utf-8")
            metadata_path = (
                attachment_store.meta_dir / f"{attachment.attachment_id}.json"
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["relative_path"] = "../../outside.txt"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outside the attachment store"):
                attachment_store.get_file_attachment(attachment.attachment_id)

    def test_delete_file_attachment_removes_materialized_workspace_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_store = AttachmentStore(root / "private-store" / "attachments")
            tool_workspace = root / "tenant-workspace"
            attachment = attachment_store.create_file_attachment(
                b"delete me",
                filename="notes.txt",
            )
            content = attachment_store.file_attachment_message_content(
                attachment.attachment_id,
                workspace=tool_workspace,
            )
            materialized_path = tool_workspace / content["workspace_path"]

            attachment_store.delete_attachment(
                attachment.attachment_id,
                workspace=tool_workspace,
            )

            self.assertFalse(materialized_path.exists())
            self.assertFalse(
                attachment_store.meta_dir.joinpath(
                    f"{attachment.attachment_id}.json"
                ).exists()
            )

    def test_create_file_attachment_from_stream_does_not_require_full_buffer(self) -> None:
        class ChunkedStream(BytesIO):
            def read(self, size: int = -1) -> bytes:
                self.assert_bounded_read(size)
                return super().read(min(size, 3))

            @staticmethod
            def assert_bounded_read(size: int) -> None:
                if size <= 0:
                    raise AssertionError("stream upload must use bounded reads")

        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")

            attachment = attachment_store.create_file_attachment_from_stream(
                ChunkedStream(b"streamed file content"),
                content_type="text/plain",
                filename="notes.txt",
            )

            self.assertEqual(21, attachment.size_bytes)
            self.assertEqual(
                b"streamed file content",
                attachment_store.file_attachment_path(attachment.attachment_id).read_bytes(),
            )

    def test_stream_file_upload_removes_partial_file_when_budget_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(
                Path(temp_dir) / "attachments",
                file_budget=FileBudget(max_input_bytes=5),
            )

            with self.assertRaisesRegex(ValueError, "upload size limit"):
                attachment_store.create_file_attachment_from_stream(
                    BytesIO(b"too large"),
                    filename="large.bin",
                )

            self.assertEqual([], list(attachment_store.files_dir.glob("*")))
            self.assertEqual([], list(attachment_store.meta_dir.glob("*")))

    def test_create_image_attachment_persists_metadata_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")

            attachment = attachment_store.create_image_attachment(
                make_png_bytes(size=(4, 3)),
                filename="demo.png",
            )

            self.assertTrue(attachment.attachment_url.startswith("attachment://"))
            self.assertTrue(attachment.preview_url.startswith("/api/attachments/"))
            self.assertEqual("demo.png", attachment.original_filename)
            self.assertEqual("demo.jpg", attachment.download_filename)
            self.assertTrue(attachment_store.image_attachment_path(attachment.attachment_id).exists())
            self.assertTrue(
                attachment_store.image_attachment_data_url(attachment.attachment_id).startswith(
                    "data:image/jpeg;base64,"
                )
            )
            metadata = json.loads(
                (attachment_store.meta_dir / f"{attachment.attachment_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("image", metadata["kind"])

    def test_image_attachment_lookup_rejects_file_attachment_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            attachment = attachment_store.create_file_attachment(
                b"hello",
                content_type="text/plain",
                filename="notes.txt",
            )

            with self.assertRaisesRegex(ValueError, "not an image"):
                attachment_store.get_image_attachment(attachment.attachment_id)

    def test_file_attachment_lookup_rejects_image_attachment_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            attachment = attachment_store.create_image_attachment(
                make_png_bytes(size=(2, 2)),
                filename="demo.png",
            )

            with self.assertRaisesRegex(ValueError, "not a file"):
                attachment_store.get_file_attachment(attachment.attachment_id)

import asyncio
import unittest

from activity import read_channel_data


class FakeAttachment:
    def __init__(self, payload):
        self.payload = payload
        self.read_calls = 0

    async def read(self):
        self.read_calls += 1
        return self.payload


class ActivityCsvTests(unittest.TestCase):
    def test_reads_attachment_in_memory(self):
        attachment = FakeAttachment(
            b"channel_name,readers,chatters,messages\n"
            b"author-room,10,4,25\n"
        )

        result = asyncio.run(read_channel_data(attachment))

        self.assertEqual(attachment.read_calls, 1)
        self.assertEqual(
            result.to_dict(orient="records"),
            [{
                "channel_name": "author-room",
                "readers": 10,
                "chatters": 4,
                "messages": 25,
            }],
        )


if __name__ == "__main__":
    unittest.main()

import struct
import unittest

from scripts.verify_artifact import disk_partitions


class PartitionTests(unittest.TestCase):
    def test_mbr_root_partition_size(self):
        header = bytearray(4096)
        header[510:512] = b"\x55\xaa"
        header[446 + 16 + 4] = 0x83
        struct.pack_into("<II", header, 446 + 16 + 8, 32768, 512 * 2048)
        table, partitions = disk_partitions(header)
        self.assertEqual(table, "MBR")
        self.assertEqual(partitions[0]["bytes"], 512 * 1024 ** 2)

    def test_invalid_signature_rejected(self):
        with self.assertRaisesRegex(ValueError, "signature"):
            disk_partitions(bytes(4096))

    def test_gpt_root_partition_size(self):
        header = bytearray(4096)
        header[510:512] = b"\x55\xaa"
        header[512:520] = b"EFI PART"
        struct.pack_into("<QII", header, 512 + 72, 2, 2, 128)
        header[1024 + 128] = 1
        struct.pack_into("<QQ", header, 1024 + 128 + 32, 33280, 33280 + 256 * 2048 - 1)
        table, partitions = disk_partitions(header)
        self.assertEqual(table, "GPT")
        self.assertEqual(partitions[0]["number"], 2)
        self.assertEqual(partitions[0]["bytes"], 256 * 1024 ** 2)


if __name__ == "__main__":
    unittest.main()

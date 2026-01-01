import argparse
import pprint

from jce import loads

parser = argparse.ArgumentParser(description="JceStruct command line tool")
parser.add_argument(
    "encoded", metavar="encoded", type=str, help="Encoded bytes in hex format"
)

args = parser.parse_args()
# 使用通用解析来解码为dict
result = loads(bytes.fromhex(args.encoded), dict)

pprint.pprint(result)

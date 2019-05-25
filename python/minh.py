from __future__ import print_function

import minnow
import struct
import numpy as np
import gc

MAGIC = 0xbaff1ed
VERSION = 0

_basic_file_type = 0
_column_buf_size = 232
_column_type = np.dtype([
    ("type", np.int64),
    ("log", np.int32),
    ("low", np.float32),
    ("high", np.float32),
    ("dx", np.float32),
    ("buf", "S%d" % _column_buf_size)
])
assert(_column_type.itemsize == 256)

def create(fname):
    return Writer(fname)

def open(fname):
    return Reader(fname)

class Column(object):
    def __init__(self, type, log=0, low=0, high=0, dx=0):
        self.type, self.log = type, log != 0
        self.low, self.high, self.dx = low, high, dx
        
class Writer(object):
    def __init__(self, fname):
        self.f = minnow.create(fname)
        self.f.header(struct.pack("<qqq", MAGIC, VERSION, _basic_file_type))
        self.blocks = 0
        self.cols = None
        self.block_sizes = []

    def header(self, names, text, cols):
        self.cols = cols
        self.f.header("$".join(names))
        self.f.header(text)
        
        bin_cols = np.zeros(len(cols), dtype=_column_type)
        for i in range(cols):
            bin_cols["type"][i] = cols[i].type
            bin_cols["log"][i] = cols[i].log
            bin_cols["low"][i] = cols[i].low
            bin_cols["high"][i] = cols[i].high
            bin_cols["dx"][i] = cols[i].dx
        
        self.f.header(bin_cols)

    def block(self, cols):
        assert(len(cols) == len(self.cols))
        for i in range(cols):
            assert(type_match(self.cols[i].type, cols[i]))

        self.block_sizes.append(len(cols[0]))
        self.blocks += 1

        for i in range(len(cols)):
            assert(len(cols) == len(cols[0]))
            col_type = self.cols[i].type

            if (col_type >= minnow.int64_group and
                col_type <= minnow.float32_group):
                self.f.fixed_size_group(col_type, len(cols[i]))
                self.f.data(cols[i])
            elif col_type == minnow.int_group:
                self.f.int_group(len(cols[i]))
                self.f.data(cols[i])
            elif col_typ == minnow.float_group:
                lim = (self.cols[i].low, self.cols[i].high)
                buf = np.asarray(np.copy(cols[i]), dtype=np.float32)
                if cols[i].log: np.log10(buf, out=buf)
                buf[buf > cols[i].high] = np.nextafter(cols[i].high, -np.inf)
                buf[buf < cols[i].low] = cols[i].low
                
                self.f.float_group(len(cols[i]), lim, self.cols[i].dx)
                self.f.data(buf)
            
    def close(self):
        self.f.header(stuct.pack("<q", self.blocks))
        self.f.header(np.array(self.block_sizes, dtype=np.int64))
        self.f.close()

class Reader(object):
    def __init__(self, fname):
        self.f = minnow.open(fname)

        magic, version, file_type = self.f.header(0, "qqq")
        assert(magic == MAGIC)
        assert(version == VERSION)

        self.names = self.f.header(1, "s").decode("ascii")
        self.text = self.f.header(2, "s").decode("ascii")
        raw_columns = self.f.header(3, _column_type)
        self.blocks = self.f.header(4, "q")
        self.block_lengths = self.f.header(5, np.int64)

        self.columns = [None]*len(raw_columns)
        for i in range(len(raw_columns)):
            self.columns[i] = Column(
                raw_columns["type"][i], raw_columns["log"][i], 
                raw_columns["low"][i], raw_columns["high"][i], 
                raw_columns["dx"][i]
            )
            
        self.names = self.names.split("$")

        self.length = np.sum(self.block_lengths)

    def read(self, names):
        blocked_out = [[None]*self.blocks for _ in range(len(names))]
        for b in range(self.blocks):
            block = self.block(b, names)
            for n in range(len(names)):
                blocked_out[n][b] = block[n]

        out = [None]*len(names)
        for n in range(len(names)):
            out[n] = np.hstack(blocked_out[n])

        return out

    def block(self, b, names):
        gc.collect()
        out = [None]*len(names)

        for i in range(len(names)):
            c = self.names.index(names[i])
            assert(c >= 0)
            
            idx = b*len(self.columns) + c
            out[i] = self.f.data(idx)

            if self.columns[c].log: out[i]=10**out[i]

        return out


    def close(self):
        self.f.close()

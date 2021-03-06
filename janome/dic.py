# -*- coding: utf-8 -*-

# Copyright 2015 moco_beta
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import with_statement
import os
import io
import pickle
import gzip
from struct import pack, unpack
from .fst import Matcher, create_minimum_transducer, compileFST
import traceback
import logging
import sys
import re

PY3 = sys.version_info[0] == 3

SYSDIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sysdic")

FILE_FST_DATA = 'fst.data'

MODULE_ENTRIES_EXTRA = 'entries_extra%d.py'
MODULE_ENTRIES_EXTRA_BUCKETS = 'entries_extra_buckets.py'  # for mmap mode
MODULE_ENTRIES_COMPACT = 'entries_compact%d.py'
MODULE_ENTRIES_COMPACT_BUCKETS = 'entries_compact_buckets.py'  # for mmap mode
MODULE_CONNECTIONS = 'connections%d.py'
MODULE_CHARDEFS = 'chardef.py'
MODULE_UNKNOWNS = 'unknowns.py'

FILE_USER_FST_DATA = 'user_fst.data'
FILE_USER_ENTRIES_DATA = 'user_entries.data'

def save_fstdata(data, dir='.'):
    _save(os.path.join(dir, FILE_FST_DATA), data, 9)


def save_entries(entries, dir=u'.'):
    # split whole entries to 10 buckets to reduce memory usage while installing.
    # TODO: find better ways...
    
    # save surface forms, costs
    bucket_size = (len(entries) // 3) + 1
    offset = 0
    buckets = {}
    for i in range(1, 4):
        _save_entries_as_module_compact(
            os.path.join(dir, MODULE_ENTRIES_COMPACT % i),
            {k:v for (k,v) in list(entries.items())[offset:offset+bucket_size]})
        buckets[i] = (offset, min(len(entries), offset+bucket_size))
        offset += bucket_size
    _save_as_module(os.path.join(dir, MODULE_ENTRIES_COMPACT_BUCKETS), buckets)

    # save extra data
    bucket_size = (len(entries) // 10) + 1
    offset = 0
    buckets = {}
    for i in range(1, 11):
        _save_entries_as_module_extra(
            os.path.join(dir, MODULE_ENTRIES_EXTRA % i),
            {k:v for (k,v) in list(entries.items())[offset:offset+bucket_size]})
        buckets[i] = (offset, min(len(entries), offset+bucket_size))
        offset += bucket_size
    _save_as_module(os.path.join(dir, MODULE_ENTRIES_EXTRA_BUCKETS), buckets)

def save_connections(connections, dir=u'.'):
    # split whole connections to 2 buckets to reduce memory usage while installing.
    # TODO: find better ways...
    bucket_size = (len(connections) // 2) + 1
    offset = 0
    for i in range(1, 3):
        _save_as_module(os.path.join(dir, MODULE_CONNECTIONS % i),
                        connections[offset:offset+bucket_size])
        offset += bucket_size


def save_chardefs(chardefs, dir=u'.'):
    _save_as_module(os.path.join(dir, MODULE_CHARDEFS), chardefs)


def save_unknowns(unknowns, dir=u'.'):
    _save_as_module(os.path.join(dir, MODULE_UNKNOWNS), unknowns)


def _save(file, data, compresslevel):
    if not data:
        return
    with gzip.open(file, 'wb', compresslevel) as f:
        f.write(data)
        f.flush()


def _load(file):
    if not os.path.exists(file):
        return None
    with gzip.open(file, 'rb') as f:
        data = f.read()
        return data


def _save_as_module(file, data):
    if not data:
        return
    with open(file, 'w') as f:
        f.write(u'DATA=')
        f.write(str(data) if PY3 else unicode(data))
        f.flush()


def _save_entries_as_module_extra(file, entries):
    idx_file = re.sub(r'\.py$', '_idx.py', file)
    with open(file, 'w') as f:
        with open(idx_file, 'w') as f_idx:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('DATA={')
            f_idx.write('DATA={')
            for k, v in entries.items():
                f.write('%d:(' % k)
                _pos1 = f.tell()
                f_idx.write('%d:%d,' % (k, _pos1))
                s = u"u'%s',u'%s',u'%s',u'%s',u'%s',u'%s'" % (
                    v[4], v[5], v[6], v[7], v[8], v[9])
                f.write(s if PY3 else s.encode('utf-8'))
                f.write('),')
            f.write('}\n')
            f.flush()
            f_idx.write('}\n')
            f_idx.flush()


def _save_entries_as_module_compact(file, entries):
    idx_file = re.sub(r'\.py$', '_idx.py', file)
    with open(file, 'w') as f:
        with open(idx_file, 'w') as f_idx:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('DATA={')
            f_idx.write('DATA={')
            for k, v in entries.items():
                f.write('%d:(' % k)
                _pos1 = f.tell()
                f_idx.write('%d:%d,' % (k, _pos1))
                s = u"u'%s',%s,%s,%d" % (v[0], v[1], v[2], v[3])
                f.write(s if PY3 else s.encode('utf-8'))
                f.write('),')
            f.write('}\n')
            f.flush()
            f_idx.write('}\n')
            f_idx.flush()


class Dictionary(object):
    u"""
    Base dictionary class
    """
    def __init__(self, compiledFST, entries, connections):
        self.compiledFST = compiledFST
        self.matcher = Matcher(compiledFST)
        self.entries = entries
        self.connections = connections

    def lookup(self, s):
        (matched, outputs) = self.matcher.run(s.encode('utf8'))
        if not matched:
            return []
        try:
            res = []
            for e in outputs:
                num = unpack('I', e)[0]
                res.append((num,) + self.entries[num][:4])
            return res
        except Exception as e:
            logging.error('Cannot load dictionary data. The dictionary may be corrupted?')
            logging.error('input=%s' % s)
            logging.error('outputs=%s' % str(outputs) if PY3 else unicode(outputs))
            traceback.format_exc()
            sys.exit(1)

    def lookup_extra(self, num):
        try:
            return self.entries[num][4:]
        except Exception as e:
            logging.error('Cannot load dictionary data. The dictionary may be corrupted?')
            logging.error('input=%s' % s)
            logging.error('outputs=%s' % str(outputs) if PY3 else unicode(outputs))
            traceback.format_exc()
            sys.exit(1)

    def get_trans_cost(self, id1, id2):
        return self.connections[id1][id2]


class MMapDictionary(object):
    u"""
    Base MMap dictionar class
    """
    def __init__(self, compiledFST, entries_compact, entries_extra, open_files, connections):
        self.compiledFST = compiledFST
        self.matcher = Matcher(compiledFST)
        self.entries_compact = entries_compact
        self.entries_extra = entries_extra
        self.open_files = open_files
        self.connections = connections

    def lookup(self, s):
        (matched, outputs) = self.matcher.run(s.encode('utf8'))
        if not matched:
            return []
        try:
            matched_entries = []
            for e in outputs:
                idx = unpack('I', e)[0]
                bucket = next(filter(lambda b: idx >= b[0] and idx < b[1], self.entries_compact.keys())) if PY3 \
                    else filter(lambda b: idx >= b[0] and idx < b[1], self.entries_compact.keys())[0]
                mm, mm_idx = self.entries_compact[bucket]
                _pos1s = mm_idx[idx] + 2
                _pos1e = mm.find(b"',", _pos1s) if PY3 else mm.find("',", _pos1s)
                _pos2s = _pos1e + 2
                _pos2e = mm.find(b",", _pos2s) if PY3 else mm.find(",", _pos2s)
                _pos3s = _pos2e + 1
                _pos3e = mm.find(b",", _pos3s) if PY3 else mm.find(",", _pos3s)
                _pos4s = _pos3e + 1
                _pos4e = mm.find(b")", _pos4s) if PY3 else mm.find(")", _pos4s)
                _entry = (mm[_pos1s:_pos1e].decode('utf-8'), int(mm[_pos2s:_pos2e]), int(mm[_pos3s:_pos3e]), int(mm[_pos4s:_pos4e]))
                matched_entries.append((idx,) + _entry)
            return matched_entries
        except Exception as e:
            logging.error('Cannot load dictionary data. The dictionary may be corrupted?')
            logging.error('input=%s' % s)
            logging.error('outputs=%s' % str(outputs) if PY3 else unicode(outputs))
            traceback.format_exc()
            sys.exit(1)

    def lookup_extra(self, idx):
        try:
            bucket = next(filter(lambda b: idx >= b[0] and idx < b[1], self.entries_extra.keys())) if PY3 \
               else filter(lambda b: idx >= b[0] and idx < b[1], self.entries_extra.keys())[0]
            mm, mm_idx = self.entries_extra[bucket]
            _pos1s = mm_idx[idx] + 2
            _pos1e = mm.find(b"',u'", _pos1s) if PY3 else mm.find("',u'", _pos1s)
            _pos2s = _pos1e + 4
            _pos2e = mm.find(b"',u'", _pos2s) if PY3 else mm.find("',u'", _pos2s)
            _pos3s = _pos2e + 4
            _pos3e = mm.find(b"',u'", _pos3s) if PY3 else mm.find("',u'", _pos3s)
            _pos4s = _pos3e + 4
            _pos4e = mm.find(b"',u'", _pos4s) if PY3 else mm.find("',u'", _pos4s)
            _pos5s = _pos4e + 4
            _pos5e = mm.find(b"',u'", _pos5s) if PY3 else mm.find("',u'", _pos5s)
            _pos6s = _pos5e + 4
            _pos6e = mm.find(b"')", _pos6s) if PY3 else mm.find("')", _pos6s)
            return (
                mm[_pos1s:_pos1e].decode('utf-8'), mm[_pos2s:_pos2e].decode('utf-8'), mm[_pos3s:_pos3e].decode('utf-8'),
                mm[_pos4s:_pos4e].decode('utf-8'), mm[_pos5s:_pos5e].decode('utf-8'), mm[_pos6s:_pos6e].decode('utf-8')
            )
        except Exception as e:
            logging.error('Cannot load extra info. The dictionary may be corrupted?')
            logging.error('idx=%d' % idx)
            traceback.format_exc()
            sys.exit(1)

    def get_trans_cost(self, id1, id2):
        return self.connections[id1][id2]

    def __del__(self):
        for mm, mm_idx in self.entries_compact.values():
            mm.close()
        if self.entries_extra:
            for mm, mm_idx in self.entries_extra.values():
                mm.close()
        for fp in self.open_files:
            fp.close()
    

class UnknownsDictionary(object):
    def __init__(self, chardefs, unknowns):
        self.char_categories = chardefs[0]
        self.char_ranges = chardefs[1]
        self.unknowns = unknowns

    def get_char_categories(self, c):
        res = {}
        for chr_range in self.char_ranges:
            if chr_range['from'] <= c <= chr_range['to']:
                cate = chr_range['cate']
                compate_cates = chr_range['compat_cates'] if 'compat_cates' in chr_range else []
                res[cate] = compate_cates
        if not res:
            res = {u'DEFAULT': []}
        return res

    def unknown_invoked_always(self, cate):
        if cate in self.char_categories:
            return self.char_categories[cate]['INVOKE']
        return False

    def unknown_grouping(self, cate):
        if cate in self.char_categories:
            return self.char_categories[cate]['GROUP']
        return False

    def unknown_length(self, cate):
        if cate in self.char_categories:
            return self.char_categories[cate]['LENGTH']
        return -1


class SystemDictionary(Dictionary, UnknownsDictionary):
    u"""
    System dictionary class
    """
    def __init__(self, entries, connections, chardefs, unknowns):
        Dictionary.__init__(self, _load(os.path.join(SYSDIC_DIR, FILE_FST_DATA)), entries, connections)
        UnknownsDictionary.__init__(self, chardefs, unknowns)


class MMapSystemDictionary(MMapDictionary, UnknownsDictionary):
    u"""
    MMap System dictionary class
    """
    def __init__(self, mmap_entries, connections, chardefs, unknowns):
        MMapDictionary.__init__(self, _load(os.path.join(SYSDIC_DIR, FILE_FST_DATA)), mmap_entries[0], mmap_entries[1], mmap_entries[2], connections)
        UnknownsDictionary.__init__(self, chardefs, unknowns)


class UserDictionary(Dictionary):
    u"""
    User dictionary class (uncompiled)
    """
    def __init__(self, user_dict, enc, type, connections):
        """
        Initialize user defined dictionary object.

        :param user_dict: user dictionary file (CSV format)
        :param enc: character encoding
        :param type: user dictionary type. supported types are 'ipadic' and 'simpledic'
        :param connections: connection cost matrix. expected value is SYS_DIC.connections

        .. seealso:: See http://mocobeta.github.io/janome/en/#use-with-user-defined-dictionary for details for user dictionary.
        """
        build_method = getattr(self, 'build' + type)
        compiledFST, entries = build_method(user_dict, enc)
        Dictionary.__init__(self, compiledFST, entries, connections)

    def buildipadic(self, user_dict, enc):
        surfaces = []
        entries = {}
        with io.open(user_dict, encoding=enc) as f:
            for line in f:
                line = line.rstrip()
                surface, left_id, right_id, cost, \
                pos_major, pos_minor1, pos_minor2, pos_minor3, \
                infl_type, infl_form, base_form, reading, phonetic = \
                    line.split(',')
                part_of_speech = ','.join([pos_major, pos_minor1, pos_minor2, pos_minor3])
                morph_id = len(surfaces)
                surfaces.append((surface.encode('utf8'), pack('I', morph_id)))
                entries[morph_id] = (surface, int(left_id), int(right_id), int(cost), part_of_speech, infl_type, infl_form, base_form, reading, phonetic)
        inputs = sorted(surfaces)  # inputs must be sorted.
        assert len(surfaces) == len(entries)
        fst = create_minimum_transducer(inputs)
        compiledFST = compileFST(fst)
        return compiledFST, entries

    def buildsimpledic(self, user_dict, enc):
        import sys
        surfaces = []
        entries = {}
        with io.open(user_dict, encoding=enc) as f:
            for line in f:
                line = line.rstrip()
                surface, pos_major, reading = line.split(',')
                part_of_speech = ','.join([pos_major, u'*', u'*', u'*'])
                morph_id = len(surfaces)
                surfaces.append((surface.encode('utf8'), pack('I', morph_id)))
                entries[morph_id] = (surface, 0, 0, -100000, part_of_speech, u'*', u'*', surface, reading, reading)
        inputs = sorted(surfaces)  # inputs must be sorted.
        assert len(surfaces) == len(entries)
        fst = create_minimum_transducer(inputs)
        compiledFST = compileFST(fst)
        return compiledFST, entries

    def save(self, to_dir, compressionlevel=9):
        u"""
        Save compressed compiled dictionary data.

        :param to_dir: directory to save dictionary data
        :compressionlevel: (Optional) gzip compression level. default is 9
        """
        if os.path.exists(to_dir) and not os.path.isdir(to_dir):
            raise Exception('Not a directory : %s' % to_dir)
        elif not os.path.exists(to_dir):
            os.makedirs(to_dir, mode=int('0755', 8))
        _save(os.path.join(to_dir, FILE_USER_FST_DATA), self.compiledFST, compressionlevel)
        _save(os.path.join(to_dir, FILE_USER_ENTRIES_DATA), pickle.dumps(self.entries), compressionlevel)


class CompiledUserDictionary(Dictionary):
    u"""
    User dictionary class (compiled)
    """
    def __init__(self, dic_dir, connections):
        compiledFST, entries = self.load_dict(dic_dir)
        Dictionary.__init__(self, compiledFST, entries, connections)

    def load_dict(self, dic_dir):
        if not os.path.exists(dic_dir) or not os.path.isdir(dic_dir):
            raise Exception('No such directory : ' % dic_dir)
        compiledFST = _load(os.path.join(dic_dir, FILE_USER_FST_DATA))
        entries = pickle.loads(_load(os.path.join(dic_dir, FILE_USER_ENTRIES_DATA)))
        return compiledFST, entries

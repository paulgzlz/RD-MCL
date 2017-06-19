#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from .. import helpers
import os
import buddysuite.SeqBuddy
import buddysuite.buddy_resources as br
import sqlite3
import pandas as pd
import numpy as np
from hashlib import md5
from time import sleep
from multiprocessing.queues import SimpleQueue
from multiprocessing import Pipe, Process
from Bio.SubsMat import SeqMat, MatrixInfo
from io import StringIO


def test_sqlitebroker_init(hf):
    tmpdir = br.TempDir()
    broker = helpers.SQLiteBroker("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    assert broker.db_file == "%s%sdb.sqlite" % (tmpdir.path, hf.sep)
    assert type(broker.connection) == sqlite3.Connection
    assert type(broker.broker_cursor) == sqlite3.Cursor
    assert type(broker.broker_queue) == SimpleQueue
    assert broker.broker is None


def test_sqlitebroker_create_table(hf):
    tmpdir = br.TempDir()
    broker = helpers.SQLiteBroker("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    broker.create_table("foo", ['id INT PRIMARY KEY', 'some_data TEXT', 'numbers INT'])
    connect = sqlite3.connect("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    cursor = connect.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    response = cursor.fetchone()
    assert response == ("foo",)
    # Try to create the table again so the method skips through the try block
    broker.create_table("foo", ['id INT PRIMARY KEY', 'some_data TEXT', 'numbers INT'])


def test_sqlitebroker_broker_loop(hf, monkeypatch, capsys):
    class MockBrokerLoopGet(object):
        def __init__(self, pipe, modes, sql="SELECT name FROM sqlite_master WHERE type='table'"):
            self.mode = self._get(modes, sql)
            self.sendpipe = pipe

        def _get(self, modes, sql):
            for _mode in modes:
                yield {'mode': _mode, 'sql': sql, 'pipe': self.sendpipe, "values": ()}

        def get(self):
            return next(self.mode)

    tmpdir = br.TempDir()
    broker = helpers.SQLiteBroker("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    broker.create_table("foo", ['id INT PRIMARY KEY', 'some_data TEXT', 'numbers INT'])

    recvpipe, sendpipe = Pipe(False)
    get_dict = {'mode': 'stop', 'sql': "SELECT name FROM sqlite_master WHERE type='table'", 'pipe': sendpipe}
    broker.broker_queue.put(get_dict)
    simple_queue_get = MockBrokerLoopGet(sendpipe, ["sql", "stop"])

    monkeypatch.setattr(SimpleQueue, 'get', simple_queue_get.get)
    broker._broker_loop(broker.broker_queue)

    connect = sqlite3.connect("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    cursor = connect.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    response = cursor.fetchone()
    assert response == ("foo",)

    # Test errors
    simple_queue_get = MockBrokerLoopGet(sendpipe, ["foo_bar"])
    monkeypatch.setattr(SimpleQueue, 'get', simple_queue_get.get)

    with pytest.raises(RuntimeError) as err:
        broker._broker_loop(broker.broker_queue)
    assert "Broker instruction 'foo_bar' not understood." in str(err)

    simple_queue_get = MockBrokerLoopGet(sendpipe, ["sql"], "NONSENSE SQL COMMAND")
    monkeypatch.setattr(SimpleQueue, 'get', simple_queue_get.get)

    with pytest.raises(sqlite3.OperationalError) as err:
        broker._broker_loop(broker.broker_queue)
    assert 'sqlite3.OperationalError: near "NONSENSE": syntax error' in str(err)
    out, err = capsys.readouterr()
    assert "Failed query: NONSENSE SQL COMMAND" in out


def test_sqlitebroker_start_and_stop_broker(hf):
    tmpdir = br.TempDir()
    broker = helpers.SQLiteBroker("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    assert broker.broker is None
    broker.start_broker()
    assert type(broker.broker) == Process
    assert broker.broker.is_alive()

    broker.stop_broker()
    assert not broker.broker.is_alive()


def test_sqlitebroker_query(hf):
    tmpdir = br.TempDir()
    broker = helpers.SQLiteBroker("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    broker.create_table("foo", ['id INT PRIMARY KEY', 'some_data TEXT', 'numbers INT'])
    with pytest.raises(RuntimeError) as err:
        broker.query("INSERT INTO foo (id, some_data, numbers) VALUES (0, 'hello', 25)")
    assert "Broker not running." in str(err)

    broker.start_broker()
    query = broker.query("INSERT INTO foo (id, some_data, numbers) VALUES (0, 'hello', 25)")
    assert query == []

    broker.close()
    connect = sqlite3.connect("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    cursor = connect.cursor()
    cursor.execute("SELECT * FROM foo")
    response = cursor.fetchone()
    assert response == (0, 'hello', 25)


def test_sqlitebroker_close(hf):
    tmpdir = br.TempDir()
    broker = helpers.SQLiteBroker("%s%sdb.sqlite" % (tmpdir.path, hf.sep))
    assert broker.broker is None
    broker.start_broker()
    assert broker.broker.is_alive()
    broker.close()
    assert not broker.broker.is_alive()


def test_logger(hf):
    tmp = br.TempFile()
    logger = helpers.Logger(tmp.path)
    assert type(logger.logger) == helpers.logging.RootLogger
    assert type(logger.console) == helpers.logging.StreamHandler
    assert logger.logger.level == 20
    assert len(logger.logger.handlers) == 2
    assert type(logger.logger.handlers[1]) == helpers.logging.StreamHandler
    assert logger.console.level == 30

    helpers.logging.info("Some info")
    helpers.logging.warning("Some Warnings")

    logger.move_log("%sfirst.log" % tmp.path)

    with open("%sfirst.log" % tmp.path, "r") as ofile:
        assert ofile.read() == "Some info\nSome Warnings\n"


def test_timer():
    timer = helpers.Timer()
    sleep(1)
    assert timer.split(prefix="start_", postfix="_end") == 'start_1 sec_end'
    sleep(1)
    assert timer.split(prefix="start_", postfix="_end") == 'start_1 sec_end'
    sleep(1)
    assert timer.total_elapsed(prefix="start_", postfix="_end") == 'start_3 sec_end'


def test_md5_hash():
    assert helpers.md5_hash("Hello") == "8b1a9953c4611296a827abf8c47804d7"


def test_make_full_mat():
    blosum62 = helpers.make_full_mat(SeqMat(MatrixInfo.blosum62))
    assert blosum62["A", "B"] == -2
    assert blosum62["B", "A"] == -2


def test_bit_score():
    assert helpers.bit_score(100) == 41.192416298119


def test_markov_clustering_init():
    data = """\
Bab\tCfu\t1
Bab\tOma\t1
Bab\tMle\t0
Cfu\tMle\t0
Cfu\tOma\t1
Oma\tMle\t0"""
    sample_df = pd.read_csv(StringIO(data), sep="\t", header=None, index_col=False)
    sample_df.columns = ["seq1", "seq2", "score"]
    mcl = helpers.MarkovClustering(sample_df, 2, 0.6)
    assert str(mcl.dataframe) == str(sample_df)
    assert mcl.inflation == 2
    assert mcl.edge_sim_threshold == 0.6
    assert mcl.name_order == ['Bab', "Cfu", "Mle", "Oma"]
    assert str(mcl.trans_matrix) == """\
[[ 0.33333333  0.33333333  0.          0.33333333]
 [ 0.33333333  0.33333333  0.          0.33333333]
 [ 0.          0.          0.          0.        ]
 [ 0.33333333  0.33333333  0.          0.33333333]]"""
    assert len(mcl.sub_state_dfs) == 1
    assert str(mcl.sub_state_dfs[0]) == """\
          0         1    2         3
0  0.333333  0.333333  0.0  0.333333
1  0.333333  0.333333  0.0  0.333333
2  0.000000  0.000000  0.0  0.000000
3  0.333333  0.333333  0.0  0.333333"""
    assert mcl.clusters == []


def test_markov_clustering_compare():
    data = """\
Bab\tCfu\t1
Bab\tOma\t1
Bab\tMle\t0
Cfu\tMle\t0
Cfu\tOma\t1
Oma\tMle\t0"""
    df = pd.read_csv(StringIO(data), sep="\t", header=None, index_col=False)
    df.columns = ["seq1", "seq2", "score"]

    mcl = helpers.MarkovClustering(df, 2)
    df1 = mcl.sub_state_dfs[0]
    df2 = mcl.sub_state_dfs[0].copy()
    assert helpers.MarkovClustering.compare(df1, df2) == 0

    df2[0][0] = 1
    df2[1][3] = 1.5
    assert round(helpers.MarkovClustering.compare(df1, df2), 1) == 1.8


def test_markov_clustering_normalize():
    matrix = np.matrix([[0., 1., 0., 1.],
                        [1., 0., 0., 1.],
                        [0., 0., 0., 0.],
                        [1., 1., 0., 0.]])
    normalized = helpers.MarkovClustering.normalize(matrix)
    assert str(normalized) == """\
[[ 0.   0.5  0.   0.5]
 [ 0.5  0.   0.   0.5]
 [ 0.   0.   0.   0. ]
 [ 0.5  0.5  0.   0. ]]"""


def test_markov_clustering_df_to_transition_matrix():
    data = """\
Bab\tCfu\t1
Bab\tOma\t1
Bab\tMle\t0
Cfu\tMle\t0
Cfu\tOma\t1
Oma\tMle\t0"""
    df = pd.read_csv(StringIO(data), sep="\t", header=None, index_col=False)
    df.columns = ["seq1", "seq2", "score"]

    mcl = helpers.MarkovClustering(df, 2)
    assert str(mcl._df_to_transition_matrix()) == """\
[[ 0.33333333  0.33333333  0.          0.33333333]
 [ 0.33333333  0.33333333  0.          0.33333333]
 [ 0.          0.          0.          0.        ]
 [ 0.33333333  0.33333333  0.          0.33333333]]"""

    mcl.dataframe = mcl.dataframe.ix[1:, :]
    with pytest.raises(ValueError) as err:
        mcl._df_to_transition_matrix()
    assert "The provided dataframe is not a symmetric graph" in str(err)


def test_markov_clustering_mcl_step():
    data = """\
Bab\tCfu\t1
Bab\tOma\t1
Bab\tMle\t0
Cfu\tMle\t1
Cfu\tOma\t1
Oma\tMle\t0"""
    df = pd.read_csv(StringIO(data), sep="\t", header=None, index_col=False)
    df.columns = ["seq1", "seq2", "score"]

    mcl = helpers.MarkovClustering(df, 2)
    mcl.mcl_step()
    assert str(mcl.trans_matrix) == """\
[[ 0.32526882  0.19771242  0.05        0.32526882]
 [ 0.32526882  0.47222222  0.45        0.32526882]
 [ 0.02419355  0.13235294  0.45        0.02419355]
 [ 0.32526882  0.19771242  0.05        0.32526882]]"""

    mcl.mcl_step()
    assert str(mcl.trans_matrix) == """\
[[ 0.25608107  0.17964133  0.06652326  0.25608107]
 [ 0.47164909  0.58116078  0.64254281  0.47164909]
 [ 0.01618877  0.05955656  0.22441067  0.01618877]
 [ 0.25608107  0.17964133  0.06652326  0.25608107]]"""

    mcl.mcl_step()
    assert str(mcl.trans_matrix) == """\
[[ 0.12636968  0.10544909  0.06773622  0.12636968]
 [ 0.74296221  0.78150128  0.84387976  0.74296221]
 [ 0.00429842  0.00760055  0.02064779  0.00429842]
 [ 0.12636968  0.10544909  0.06773622  0.12636968]]"""

    mcl.mcl_step()
    assert str(mcl.trans_matrix) == """\
[[  1.97036886e-02   1.92752312e-02   1.84096262e-02   1.97036886e-02]
 [  9.60517622e-01   9.61370799e-01   9.63092986e-01   9.60517622e-01]
 [  7.50011699e-05   7.87382116e-05   8.77612448e-05   7.50011699e-05]
 [  1.97036886e-02   1.92752312e-02   1.84096262e-02   1.97036886e-02]]"""


def test_markov_clustering_run(monkeypatch):
    data = """\
Bab\tCfu\t0.9
Bab\tOma\t0.1
Bab\tMle\t0.1
Cfu\tMle\t0.1
Cfu\tOma\t0.1
Oma\tMle\t0.9"""
    df = pd.read_csv(StringIO(data), sep="\t", header=None, index_col=False)
    df.columns = ["seq1", "seq2", "score"]

    mcl = helpers.MarkovClustering(df, 2)
    mcl.run()
    assert str(mcl.trans_matrix) == """\
[[ 0.5  0.5  0.   0. ]
 [ 0.5  0.5  0.   0. ]
 [ 0.   0.   0.5  0.5]
 [ 0.   0.   0.5  0.5]]"""
    assert mcl.clusters == [["Mle", "Oma"], ['Bab', "Cfu"]]

    def safetyvalve_init(self, global_reps):
        self.counter = 0
        self.global_reps = 2

    monkeypatch.setattr(br.SafetyValve, "__init__", safetyvalve_init)
    mcl = helpers.MarkovClustering(df, 2)
    mcl.run()
    assert mcl.clusters[0] == ['Bab', "Cfu", "Mle", "Oma"]


def test_markov_clustering_write():
    data = """\
Bab\tCfu\t0.3
Bab\tOma\t0.5
Bab\tMle\t0
Cfu\tMle\t0.7
Cfu\tOma\t0.7
Oma\tMle\t0"""
    df = pd.read_csv(StringIO(data), sep="\t", header=None, index_col=False)
    df.columns = ["seq1", "seq2", "score"]

    mcl = helpers.MarkovClustering(df, 2)
    mcl.run()

    tmp_file = br.TempFile()
    mcl.write(tmp_file.path)
    assert tmp_file.read() == "Bab	Cfu	Mle	Oma\n"

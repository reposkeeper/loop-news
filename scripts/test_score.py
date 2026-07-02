#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""score.py 单元测试(标准库 unittest,无新依赖)。
覆盖:反作弊-克制、反作弊-创新、composite=8者均值、向后兼容(prev 只有 6 分时 delta 为 None)。
跑法:python3 scripts/test_score.py   或   python3 -m unittest scripts/test_score.py
"""
import json, os, sys, io, shutil, tempfile, contextlib, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 让两种跑法都能 import score
import score  # noqa: E402


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class RestraintAntiCheatTest(unittest.TestCase):
    """大胆结论堆砌但证据<2 → restraint 明显低于『都有≥2证据且分级克制』。"""

    def test_bold_pile_scores_lower(self):
        corpus = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        # 克制:每条大胆结论都有 ≥2 证据、预测占比健康(1/4)、预测带 confidence
        good = {"connections": [], "conclusions": [
            {"grade": "事实", "evidence": ["a", "b"], "confidence": 0.9},
            {"grade": "推断", "evidence": ["a", "b"], "confidence": 0.7},
            {"grade": "推断", "evidence": ["b", "c"], "confidence": 0.6},
            {"grade": "预测", "evidence": ["a", "c"], "confidence": 0.55},
        ]}
        # 越界:大胆结论堆砌,证据都 <2,预测占比过高
        bad = {"connections": [], "conclusions": [
            {"grade": "推断", "evidence": ["a"]},
            {"grade": "预测", "evidence": ["b"]},
            {"grade": "预测", "evidence": []},
            {"grade": "推断", "evidence": ["c"]},
        ]}
        g, gc = score.restraint_score(good, corpus)
        b, bc = score.restraint_score(bad, corpus)
        self.assertGreater(g, b)
        self.assertGreater(g - b, 30, f"克制差距应显著: good={g} bad={b}")
        self.assertEqual(gc["overreach_rate"], 0.0)   # good 无越界
        self.assertEqual(bc["overreach_rate"], 1.0)    # bad 全越界
        self.assertEqual(gc["grounded"], 1.0)

    def test_prediction_missing_confidence_is_overreach(self):
        # schema 有 confidence 字段(某条带) → 预测缺 confidence 也算越界
        corpus = [{"id": "a"}, {"id": "b"}]
        a = {"connections": [], "conclusions": [
            {"grade": "事实", "evidence": ["a", "b"], "confidence": 0.9},
            {"grade": "预测", "evidence": ["a", "b"]},  # 证据够但缺 confidence
        ]}
        _s, c = score.restraint_score(a, corpus)
        self.assertEqual(c["overreach_rate"], 1.0)  # 唯一的 bold(预测)因缺置信度而越界


class InnovationAntiCheatTest(unittest.TestCase):
    """core 占比高 + 全是旧 topic → innovation 明显低于『有新 topic/实体 + 低 core 占比』。"""

    def test_stale_high_core_scores_lower(self):
        # 低分:全是昨天见过的 topic、from_core 高、透镜单一、无跨域
        low_conns = [{"lens": "时间线追踪", "evidence": ["p"]}]
        low_map = {"p": {"topics": ["AI"]}}
        low, lc = score.innovation_score(
            today_tokens={"AI", "芯片"}, prior_seen={"AI", "芯片"}, from_core_share=0.9,
            conns=low_conns, corpus_by_id=low_map, prior_pairs=set(),
            prev_scores=None, cur_partial={}, targets=score.TARGETS)
        # 高分:6 个全新 token、from_core 低、冷门透镜多、跨域新配对
        high_conns = [
            {"lens": "跟着钱走 / 跨域模式", "evidence": ["x", "y"]},
            {"lens": "二阶效应", "evidence": ["y", "z"]},
            {"lens": "共识缺口 / 矛盾检测", "evidence": ["x", "z"]},
        ]
        high_map = {"x": {"topics": ["t1", "t2"]}, "y": {"topics": ["t3", "t4"]}, "z": {"topics": ["t5", "t6"]}}
        high, hc = score.innovation_score(
            today_tokens={"量子", "生物", "脑机", "材料", "新体X", "新体Y"}, prior_seen=set(), from_core_share=0.1,
            conns=high_conns, corpus_by_id=high_map, prior_pairs=set(),
            prev_scores=None, cur_partial={}, targets=score.TARGETS)
        self.assertGreater(high, low)
        self.assertGreater(high - low, 40, f"创新差距应显著: high={high} low={low}")
        self.assertEqual(lc["new_productive"], 0.0)     # 全旧 → 无新产出
        self.assertEqual(hc["new_productive"], 1.0)     # 6 个新 token 达标
        self.assertLess(lc["exploration"], hc["exploration"])  # 高 core → 低探索

    def test_learning_velocity_direction(self):
        prev = {"correlation": 80.0, "volume": 20.0, "analysis": 70.0, "composite": 60.0}  # 最弱=volume(20)
        # 本轮 volume 上升 → 1.0
        self.assertEqual(score._learning_velocity(prev, {"volume": 30.0}), 1.0)
        # 持平 → 0.5
        self.assertEqual(score._learning_velocity(prev, {"volume": 20.0}), 0.5)
        # 下滑 → 0.0
        self.assertEqual(score._learning_velocity(prev, {"volume": 10.0}), 0.0)
        # 无上一 entry → 0.5
        self.assertEqual(score._learning_velocity(None, {"volume": 10.0}), 0.5)


class _RootFixture(unittest.TestCase):
    """把 score.ROOT 指到临时目录,喂受控的 analysis/corpus,跑真实 main()。"""

    DATE = "2026-07-02"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_root = score.ROOT
        score.ROOT = self.tmp
        analysis = {"connections": [{"lens": "跟着钱走 / 跨域模式", "evidence": ["a", "b"]}],
                    "conclusions": [
                        {"grade": "事实", "evidence": ["a", "b"], "confidence": 0.9},
                        {"grade": "推断", "evidence": ["a", "b"], "confidence": 0.7},
                        {"grade": "预测", "evidence": ["a", "c"], "confidence": 0.6}]}
        corpus = [{"id": i, "category": "consensus", "topics": ["AI", "芯片"], "entities": [],
                   "source": "X", "published": self.DATE} for i in ("a", "b", "c")]
        _write(os.path.join(self.tmp, f"data/analysis/{self.DATE}.json"), analysis)
        _write(os.path.join(self.tmp, f"data/corpus/{self.DATE}.json"), corpus)
        _write(os.path.join(self.tmp, "data/source_quality.json"),
               {"sources": {"X": {"tier": "core", "quality": 0.8}}, "last_curation": self.DATE})
        _write(os.path.join(self.tmp, "data/entities/index.json"), {})
        os.makedirs(os.path.join(self.tmp, "state"), exist_ok=True)  # main() 写 state/scores.json

    def tearDown(self):
        score.ROOT = self.orig_root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        argv = sys.argv
        sys.argv = ["score.py", self.DATE]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                score.main()
        finally:
            sys.argv = argv
        with open(os.path.join(self.tmp, "state/scores.json"), encoding="utf-8") as f:
            store = json.load(f)
        entry = next(h for h in store["history"] if h["date"] == self.DATE)
        return entry, buf.getvalue()


class CompositeTest(_RootFixture):
    def test_composite_is_8_mean(self):
        entry, out = self._run()
        s = entry["scores"]
        dims = ["correlation", "volume", "analysis", "breadth",
                "source_quality", "timeliness", "restraint", "innovation"]
        for k in dims:
            self.assertIn(k, s)                      # 8 个维度都在
        self.assertEqual(s["composite"], round(sum(s[k] for k in dims) / 8, 1))
        self.assertIn("克制", out)                     # 打印行扩展到 8 分
        self.assertIn("创新", out)
        # TARGETS 新键写进 store["targets"]
        with open(os.path.join(self.tmp, "state/scores.json"), encoding="utf-8") as f:
            store = json.load(f)
        for k in ("novelty_window", "novel_target", "lens_target", "cross_domain_target"):
            self.assertIn(k, store["targets"])


class BackwardCompatTest(_RootFixture):
    def test_prev_six_scores_delta_none(self):
        # 旧 entry 只有 6 分
        _write(os.path.join(self.tmp, "state/scores.json"), {"targets": {}, "history": [{
            "date": "2026-06-30",
            "scores": {"correlation": 50.0, "volume": 50.0, "analysis": 50.0,
                       "breadth": 50.0, "source_quality": 50.0, "timeliness": 50.0, "composite": 50.0},
            "components": {}, "delta_vs_prev": {}}]})
        entry, _out = self._run()  # 不得抛异常
        d = entry["delta_vs_prev"]
        self.assertIsNone(d["restraint"])      # prev 无此键 → None(不是 new−0)
        self.assertIsNone(d["innovation"])
        self.assertIsNotNone(d["composite"])   # composite 在 prev 中 → 数值
        self.assertIsInstance(d["correlation"], float)


if __name__ == "__main__":
    unittest.main(verbosity=2)

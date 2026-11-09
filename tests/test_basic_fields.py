"""Offline regressions for planning input; no API calls or user databases."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class BasicFieldTests(unittest.TestCase):
    def setUp(self):
        name = '_basic_field_regression'
        package = types.ModuleType(name)
        package.__path__ = []
        llm = types.ModuleType(name + '.llm')
        llm.LlmError = type('LlmError', (RuntimeError,), {})
        llm.chat_json = MagicMock(return_value={'field': 'unknown'})
        store = types.ModuleType(name + '.store')
        for method in ('search_memory', 'set_session', 'get_session', 'add_message', 'get_profile', 'add_memory'):
            setattr(store, method, MagicMock())
        store.search_memory.return_value = []
        store.get_profile.return_value = {}
        tools = types.ModuleType(name + '.tools')
        tools.tools_spec = lambda: []
        tools.browser_session = MagicMock()
        competitions = types.ModuleType(name + '.competitions')
        competitions.recommend_competitions = MagicMock()
        modules = {name: package, name + '.llm': llm, name + '.store': store,
                   name + '.tools': tools, name + '.competitions': competitions}
        source = Path(__file__).resolve().parents[1] / 'agent' / 'workflow.py'
        spec = importlib.util.spec_from_file_location(name + '.workflow', source)
        self.workflow = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.workflow)
        self.llm, self.store = llm, store

    def test_city_answer_after_school_and_major_advances_to_companies(self):
        for reply, city in [('武汉', '武汉'), ('武汉市', '武汉市'), ('学校在湖北省武汉市。', '湖北省武汉市'), ('洛阳', '洛阳')]:
            with self.subTest(reply=reply):
                state = {'step': 'city', 'mode': 'plan', 'pending': ['city'],
                         'school': '武汉工程学院', 'major': '机器人工程',
                         'degree': '本科', 'degree_type': '普通本科', 'study_years': '4年'}
                self.store.get_session.return_value = state
                events = []
                with patch.object(self.workflow, '_list_companies', return_value='测试企业') as recommend:
                    self.workflow.run('city-test', reply, lambda e,d: events.append((e,d)))
                self.assertEqual(state.get('city'), city)
                self.assertEqual(state['step'], 'company')
                self.assertEqual(recommend.call_args.args[:3], ('机器人工程', city, '武汉工程学院'))
                answer = ''.join(d['delta'] for e,d in events if e == 'content')
                self.assertIn('意向公司', answer)
                self.assertNotIn('所在城市在哪', answer)
        self.llm.chat_json.assert_not_called()

    def test_city_confirmation_does_not_save_confirmation_word(self):
        state = {'step': 'city', 'pending': ['city', 'major']}
        self.store.get_session.return_value = state
        self.workflow._handle_basic_field('test', state, '确认', {}, MagicMock(), False)
        self.assertNotIn('city', state)
        self.assertEqual(state['step'], 'city')
        self.workflow._handle_basic_field('test', state, '确认', {'user_city': '宜昌'}, MagicMock(), False)
        self.assertEqual((state['city'], state['step']), ('宜昌', 'major'))
        self.llm.chat_json.assert_not_called()

    def test_retry_company_lookup_keeps_city(self):
        for use_button in (True, False):
            with self.subTest(use_button=use_button):
                state = {'step': 'city', 'pending': ['city'], 'mode': 'plan', 'school': '武汉工程学院',
                         'major': '机器人工程', 'degree': '本科', 'study_years': '4年'}
                self.store.get_session.return_value = state
                with patch.object(self.workflow, '_list_companies', side_effect=[self.llm.LlmError('offline'), '测试企业']) as lookup:
                    self.workflow.run('retry-test', '武汉')
                    self.assertEqual((state['city'], state['step']), ('武汉', 'recommend_companies'))
                    if use_button:
                        self.workflow.retry_last('retry-test', None, False)
                    else:
                        self.workflow.run('retry-test', '重试')
                    self.assertEqual((state['city'], state['step']), ('武汉', 'company'))
                    self.assertEqual(lookup.call_args_list[0].args[:4], lookup.call_args_list[1].args[:4])
        self.llm.chat_json.assert_not_called()

    def test_explicit_school_names_do_not_need_model(self):
        self.llm.chat_json.side_effect = self.llm.LlmError('API unavailable')
        for text in ('武汉工程大学', '北京大学', '武汉职业技术学院', '武汉工程大学。'):
            with self.subTest(text=text):
                self.assertEqual(self.workflow._classify_field(text, 'school', {}, {}), 'school')
        self.llm.chat_json.assert_not_called()

    def test_school_answer_is_saved_and_advances_to_degree(self):
        self.llm.chat_json.side_effect = self.llm.LlmError('API unavailable')
        state = {'step': 'school', 'mode': 'plan',
                 'pending': list(self.workflow._BASIC_FIELDS)}
        self.store.get_session.return_value = state
        events = []
        self.workflow._handle_basic_field('test', state, '武汉工程大学', {},
                                          lambda event, data: events.append((event, data)), False)
        self.assertEqual(state['school'], '武汉工程大学')
        self.assertEqual(state['step'], 'degree')
        self.assertNotIn('school', state['pending'])
        self.store.set_session.assert_called_once_with('test', state)
        response = ''.join(data['delta'] for event, data in events if event == 'content')
        self.assertIn('你的学历', response)
        self.assertNotIn('你的学校是?', response)

    def test_api_failure_surfaces_and_keeps_current_question_pending(self):
        self.llm.chat_json.side_effect = self.llm.LlmError('API unavailable')
        state = {'step': 'city', 'pending': ['city', 'major']}
        emit = MagicMock()
        with self.assertRaises(self.llm.LlmError):
            self.workflow._handle_basic_field('test', state, '请根据我的学校推断所在城市', {}, emit, False)
        self.assertEqual(state, {'step': 'city', 'pending': ['city', 'major']})
        self.store.set_session.assert_not_called()
        emit.assert_not_called()

    def test_model_can_return_degree_type(self):
        self.llm.chat_json.return_value = {'field': 'degree_type'}
        self.assertEqual(self.workflow._classify_field('普通的', 'degree_type', {}, {}), 'degree_type')

    def test_degree_type_answer_advances(self):
        self.llm.chat_json.return_value = {'field': 'degree_type'}
        state = {'step': 'degree_type', 'degree': '本科', 'pending': ['degree_type', 'major']}
        self.store.get_session.return_value = state
        self.workflow._handle_basic_field('test', state, '普通的', {}, MagicMock(), False)
        self.assertEqual(state['degree_type'], '普通的')
        self.assertEqual(state['step'], 'major')

    def test_existing_confirmation_uses_saved_school(self):
        profile = {'user_school': '武汉工程大学'}
        self.assertEqual(self.workflow._classify_field('确认', 'school', {}, profile), 'school')
        self.llm.chat_json.assert_not_called()

    def test_non_school_text_uses_model(self):
        self.llm.chat_json.return_value = {'field': 'major'}
        self.assertEqual(self.workflow._classify_field('我要学习机械制图', 'school', {}, {}), 'major')
        self.llm.chat_json.assert_called_once()

    def test_unknown_input_does_not_advance(self):
        state = {'step': 'school', 'pending': ['school', 'degree']}
        self.store.get_session.return_value = state
        self.workflow._handle_basic_field('test', state, '随便', {}, MagicMock(), False)
        self.assertEqual(state['step'], 'school')
        self.assertEqual(state['pending'], ['school', 'degree'])
        self.store.set_session.assert_not_called()

    def test_existing_precise_rules_remain_available_offline(self):
        for text, field in [('本科', 'degree'), ('普通本科', 'degree_type'),
                            ('职业本科', 'degree_type'), ('4年', 'study_years')]:
            with self.subTest(text=text):
                self.assertEqual(self.workflow._classify_field(text, 'school', {}, {}), field)
        self.llm.chat_json.assert_not_called()

    def test_catalog_codes_and_names_are_resolved_without_api(self):
        self.llm.chat_json.side_effect = self.llm.LlmError('API unavailable')
        for catalog in (self.workflow.MAJOR_DB, self.workflow.MAJOR_DB_VOC):
            for entries in catalog.values():
                for entry in entries:
                    code, name = entry[:2]
                    with self.subTest(code=code):
                        self.assertEqual(self.workflow._resolve_major_input(code), name)
                        self.assertEqual(self.workflow._classify_field(code, 'major', {}, {}), 'major')
                        self.assertEqual(self.workflow._classify_field(name, 'major', {}, {}), 'major')
        self.llm.chat_json.assert_not_called()

    def test_major_code_is_saved_as_name_and_advances(self):
        for text, name in [('080803T', '机器人工程'), ('080303t', '智能感知工程'),
                           ('080201 机械工程', '机械工程'), ('460301', '机电一体化技术'),
                           ('自动化', '自动化')]:
            with self.subTest(text=text):
                state = {'step': 'major', 'school': '武汉工程大学',
                         'degree': '本科', 'pending': ['major', 'study_years', 'city']}
                self.store.get_session.return_value = state
                events = []
                self.workflow._handle_basic_field('test', state, text, {},
                    lambda event, data: events.append((event, data)), False)
                self.assertEqual(state['major'], name)
                self.assertEqual(state['step'], 'study_years')
                self.assertEqual(state['school'], '武汉工程大学')
                response = ''.join(d['delta'] for e, d in events if e == 'content')
                self.assertIn('学制', response)
        self.llm.chat_json.assert_not_called()

    def test_invalid_or_partial_code_explains_without_advancing(self):
        self.llm.chat_json.return_value = {'field': 'major'}
        for text in ('0803T', '0803', '999999', '080803', '080803K'):
            with self.subTest(text=text):
                state = {'step': 'major', 'pending': ['major', 'study_years']}
                self.store.get_session.return_value = state
                events = []
                self.workflow._handle_basic_field('test', state, text, {},
                    lambda event, data: events.append((event, data)), False)
                self.assertNotIn('major', state)
                self.assertEqual(state['step'], 'major')
                response = ''.join(d['delta'] for e, d in events if e == 'content')
                self.assertIn('完整专业代码', response)
                self.assertNotIn('普通高等学校本科专业目录', response)
        self.llm.chat_json.assert_not_called()
        self.store.set_session.assert_not_called()

    def test_unsupported_major_name_still_uses_semantic_classifier(self):
        self.llm.chat_json.return_value = {'field': 'major'}
        state = {'step': 'major', 'pending': ['major', 'study_years']}
        self.store.get_session.return_value = state
        self.workflow._handle_basic_field('test', state, '土木工程', {}, MagicMock(), False)
        self.assertEqual(state['major'], '土木工程')
        self.assertEqual(state['step'], 'study_years')
        self.llm.chat_json.assert_called_once()

    def test_unknown_major_input_gets_short_help(self):
        state = {'step': 'major', 'pending': ['major', 'study_years']}
        self.store.get_session.return_value = state
        events = []
        self.workflow._handle_basic_field('test', state, '随便', {},
            lambda event, data: events.append((event, data)), False)
        response = ''.join(d['delta'] for e, d in events if e == 'content')
        self.assertIn('暂未识别', response)
        self.assertLess(len(response), 100)
        self.assertEqual(state['step'], 'major')

    def test_question_explains_full_code_option(self):
        for degree in ('本科', '专科'):
            response = self.workflow._major_question({'degree': degree}, {})
            self.assertIn('完整专业代码', response)
            self.assertIn('含字母后缀', response)

    def test_unknown_model_field_is_rejected(self):
        self.llm.chat_json.return_value = {'field': 'unrecognized'}
        self.assertEqual(self.workflow._classify_field('其他信息', 'school', {}, {}), 'unknown')


if __name__ == '__main__':
    unittest.main()

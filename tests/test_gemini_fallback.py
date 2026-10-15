import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from scripts.update_podcast import GeminiClient, GeminiRequestError, decide_study_words, is_quota_exhausted


@patch('scripts.update_podcast.time.sleep')
class GeminiFallbackTests(unittest.TestCase):
    def make_client(self, paid=True):
        with patch('google.genai.Client') as constructor:
            free_client, paid_client = Mock(), Mock()
            constructor.side_effect = [free_client, paid_client]
            client = GeminiClient('free', 'paid' if paid else None)
            for args in constructor.call_args_list:
                self.assertEqual(args.kwargs['http_options']['retry_options']['attempts'], 1)
        return client, free_client, paid_client

    def test_free_success(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.return_value = SimpleNamespace(output_text='{"ok": true}')
        self.assertEqual(client.generate_json(prompt='test', schema={}), {'ok': True})
        free.interactions.create.assert_called_once()
        paid.interactions.create.assert_not_called()
        sleep.assert_not_called()

    def test_quota_exhaustion_switches_immediately(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.side_effect = RuntimeError('429 RESOURCE_EXHAUSTED: You exceeded your current quota')
        paid.interactions.create.return_value = SimpleNamespace(output_text='{}')
        self.assertEqual(client.generate_json(prompt='test', schema={}), {})
        free.interactions.create.assert_called_once()
        paid.interactions.create.assert_called_once()
        sleep.assert_not_called()

    def test_daily_rate_limit_switches_immediately_without_quota_word(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.side_effect = RuntimeError(
            '429 Rate limit exceeded for model gemini-3.6-flash '
            '(limit: 20 requests per day on Free Tier). Please retry in 9h12m46s'
        )
        paid.interactions.create.return_value = SimpleNamespace(output_text='{}')
        self.assertEqual(client.generate_json(prompt='test', schema={}), {})
        free.interactions.create.assert_called_once()
        paid.interactions.create.assert_called_once()
        sleep.assert_not_called()

    def test_quota_after_transient_failure_skips_transition_wait(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.side_effect = [RuntimeError('503'), RuntimeError('Quota exceeded for metric: free_tier')]
        paid.interactions.create.return_value = SimpleNamespace(output_text='{}')
        self.assertEqual(client.generate_json(prompt='test', schema={}), {})
        self.assertEqual(free.interactions.create.call_count, 2)
        sleep.assert_called_once_with(30)

    def test_paid_failures_after_quota_exhaustion_keep_retry_limit(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.side_effect = RuntimeError('quota exhausted')
        paid.interactions.create.side_effect = RuntimeError('paid quota exhausted')
        with self.assertRaisesRegex(GeminiRequestError, '4 attempts'):
            client.generate_json(prompt='test', schema={})
        free.interactions.create.assert_called_once()
        self.assertEqual(paid.interactions.create.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(30)] * 2)

    def test_quota_without_paid_key_fails_immediately(self, sleep):
        client, free, _ = self.make_client(paid=False)
        free.interactions.create.side_effect = RuntimeError('quota exhausted')
        with self.assertRaisesRegex(GeminiRequestError, 'no paid key configured'):
            client.generate_json(prompt='test', schema={})
        free.interactions.create.assert_called_once()
        sleep.assert_not_called()

    def test_quota_detection(self, sleep):
        error = RuntimeError('429')
        error.response_json = {'error': {'message': 'Quota exceeded for metric: free_tier'}}
        self.assertTrue(is_quota_exhausted(error))
        for message in ('429', '429 Too Many Requests', '503 no capacity', 'RESOURCE_EXHAUSTED',
                        '429 Rate limit exceeded (limit: 10 requests per minute)'):
            self.assertFalse(is_quota_exhausted(RuntimeError(message)))

    def test_free_recovers_on_third_attempt(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.side_effect = [RuntimeError('503'), RuntimeError('503'), SimpleNamespace(output_text='{}')]
        self.assertEqual(client.generate_json(prompt='test', schema={}), {})
        self.assertEqual(free.interactions.create.call_count, 3)
        paid.interactions.create.assert_not_called()
        self.assertEqual(sleep.call_args_list, [call(30)] * 2)

    def test_paid_recovers_on_third_attempt_in_order(self, sleep):
        client, free, paid = self.make_client()
        events = Mock()
        events.attach_mock(free.interactions.create, 'free')
        events.attach_mock(paid.interactions.create, 'paid')
        events.attach_mock(sleep, 'sleep')
        free.interactions.create.side_effect = RuntimeError('429')
        paid.interactions.create.side_effect = [RuntimeError('503'), RuntimeError('503'), SimpleNamespace(output_text='{}')]
        self.assertEqual(client.generate_json(prompt='test', schema={}), {})
        self.assertEqual([event[0] for event in events.mock_calls],
                         ['free', 'sleep', 'free', 'sleep', 'free', 'sleep', 'paid', 'sleep', 'paid', 'sleep', 'paid'])
        self.assertEqual(sleep.call_args_list, [call(30)] * 5)

    def test_all_failures_raise_without_final_sleep(self, sleep):
        for message in ('400 invalid schema', '429', 'timeout'):
            with self.subTest(message=message):
                sleep.reset_mock()
                client, free, paid = self.make_client()
                free.interactions.create.side_effect = RuntimeError(message)
                last_error = RuntimeError('paid failed')
                paid.interactions.create.side_effect = last_error
                with self.assertRaisesRegex(GeminiRequestError, '6 attempts') as raised:
                    client.generate_json(prompt='test', schema={})
                self.assertIs(raised.exception.__cause__, last_error)
                self.assertEqual(free.interactions.create.call_count, 3)
                self.assertEqual(paid.interactions.create.call_count, 3)
                self.assertEqual(sleep.call_args_list, [call(30)] * 5)

    def test_empty_and_invalid_json_responses_retry(self, sleep):
        client, free, paid = self.make_client()
        free.interactions.create.side_effect = [SimpleNamespace(output_text=''), SimpleNamespace(output_text='invalid'), SimpleNamespace(output_text='')]
        paid.interactions.create.return_value = SimpleNamespace(output_text='{}')
        self.assertEqual(client.generate_json(prompt='test', schema={}), {})
        self.assertEqual(free.interactions.create.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(30)] * 3)

    def test_missing_paid_key(self, sleep):
        client, free, _ = self.make_client(paid=False)
        free.interactions.create.side_effect = RuntimeError('failed')
        with self.assertRaisesRegex(GeminiRequestError, '3 attempts'):
            client.generate_json(prompt='test', schema={})
        self.assertEqual(free.interactions.create.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(30)] * 2)

    def test_transcription_retries_and_cleans_up(self, sleep):
        client, free, paid = self.make_client()
        for sdk in (free, paid):
            sdk.files.upload.return_value = SimpleNamespace(name='file', uri='uri', mime_type='audio/mp3')
        free.interactions.create.side_effect = RuntimeError('503')
        paid.interactions.create.return_value = SimpleNamespace(output_text='transcript')
        self.assertEqual(client.transcribe(Path('episode.mp3')), 'transcript')
        self.assertEqual(free.files.delete.call_count, 3)
        paid.files.delete.assert_called_once_with(name='file')
        self.assertEqual(sleep.call_args_list, [call(30)] * 3)

    def test_vocabulary_propagates_exhausted_retries(self, sleep):
        client = Mock()
        client.generate_json.side_effect = GeminiRequestError('all attempts failed')
        with self.assertRaises(GeminiRequestError):
            decide_study_words(client, [{'word': 'learning', 'kkPhonetic': '/test/',
                                         'partOfSpeech': 'noun', 'meaningZh': '學習',
                                         'example': 'Learning is fun.'}])


if __name__ == '__main__':
    unittest.main()

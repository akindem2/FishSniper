import unittest

from fishing import FishSolBot


class InitialPathingTests(unittest.TestCase):
    def test_toggle_on_rearms_initial_pathing_for_macro_start(self):
        bot = FishSolBot()
        bot.has_done_initial_pathing = True

        bot.toggle_on()

        self.assertFalse(bot.has_done_initial_pathing)

    def test_prepare_for_server_join_does_not_reset_initial_pathing(self):
        bot = FishSolBot()
        bot.has_done_initial_pathing = True

        bot.prepare_for_server_join()

        self.assertTrue(bot.has_done_initial_pathing)
        self.assertTrue(bot.is_waiting_for_start_button)

    def test_toggle_on_can_skip_initial_pathing_reset_for_server_join(self):
        bot = FishSolBot()
        bot.has_done_initial_pathing = True

        bot.toggle_on(reset_initial_pathing=False)

        self.assertTrue(bot.has_done_initial_pathing)


if __name__ == "__main__":
    unittest.main()

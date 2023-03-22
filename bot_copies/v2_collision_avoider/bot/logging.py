import logging


class BehaviourLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        prefix = '{0.game_state.real_env_steps} - {0.unit_id} - '.format(self.extra["behaviour"])
        return '{0}{1}'.format(prefix, msg), kwargs

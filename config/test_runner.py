from django.test.runner import DiscoverRunner


class ProjectTestRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        # Discover every application, without traversing installed vendor/agent caches.
        return super().run_tests(test_labels or ['catalog', 'cart', 'users'], **kwargs)

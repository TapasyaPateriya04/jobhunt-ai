"""Job scrapers. ``scrape_jobs`` is re-exported lazily from :mod:`scraper.service`."""


def scrape_jobs(*args, **kwargs):
    from scraper.service import scrape_jobs as _scrape_jobs

    return _scrape_jobs(*args, **kwargs)

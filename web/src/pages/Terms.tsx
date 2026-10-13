/* Terms and conditions, linked from the footer of every page. Keep it in step with
   ui/pages/terms.py. */
export function Terms() {
  return (
    <>
      <h1>Terms and conditions</h1>
      <p className="hint">Last updated 13 October 2026</p>

      <p>
        These terms cover your use of JobHunt AI, a personal job-search tool that you run on your own computer. By
        running the app you agree to them.
      </p>

      <h2>What the app does</h2>
      <p>
        The app collects job postings from public sources, scores each one against your resume and helps you draft
        cover letters and resume changes. It is a helper for your own job search, not a recruiting service, and
        nobody reviews your applications on your behalf.
      </p>

      <h2>Your responsibilities</h2>
      <ul>
        <li>
          <b>Check everything you send.</b> Match scores are estimates from keyword and text comparison. Drafts
          written by a language model can be wrong or overstate your experience. The app flags claims it cannot
          find in your resume, but it can miss some. Read and correct every draft before you send it to an
          employer.
        </li>
        <li>
          <b>Respect the job sites.</b> The built-in sources are public APIs and job boards whose robots.txt allows
          the app, and the app limits how often it asks them. LinkedIn and Naukri do not allow automated access. If
          you turn them on in <code>.env</code>, you do so against those sites' terms and at your own risk,
          including the risk that they block you.
        </li>
        <li>
          <b>Keep your keys private.</b> If you add a Gemini API key, it is yours to protect, and your use of
          Gemini is covered by Google's terms.
        </li>
        <li>
          <b>Use it for your own search.</b> Do not use the app to collect jobs for resale or to send bulk
          applications.
        </li>
      </ul>

      <h2>Job postings</h2>
      <p>
        Postings belong to the employers and sites that published them. The app shows them as it received them and
        cannot confirm that a job is real, still open or accurately described. Always apply through the employer's
        own page.
      </p>

      <h2>No warranty</h2>
      <p>
        The app is provided as it is, without any warranty. It may contain bugs, a source may stop working, and
        stored data can be lost if your computer fails, so keep backups (the app can export your jobs as CSV). To
        the extent the law allows, the author is not liable for any loss that comes from using it, including a
        missed or failed application.
      </p>

      <h2>Changes</h2>
      <p>These terms can change as the app changes. The date above shows the latest version.</p>
    </>
  );
}

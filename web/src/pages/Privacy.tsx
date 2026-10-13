/* Privacy policy, linked from the footer of every page. Keep it in step with
   ui/pages/privacy.py: when data handling changes, both change in the same commit. */
export function Privacy() {
  return (
    <>
      <h1>Privacy policy</h1>
      <p className="hint">Last updated 13 October 2026</p>

      <p>
        JobHunt AI is a personal job-search tool that runs on your own computer. There is no account, no server run
        by us and no usage tracking. This page says what the app stores, where it keeps it, and the few cases in
        which something leaves your computer.
      </p>

      <h2>What the app stores</h2>
      <p>Everything is kept on your computer:</p>
      <ul>
        <li>
          <b>Your resume.</b> A copy of the file you upload goes to the <code>uploads</code> folder inside your
          documents folder (<code>DOCS_DIR</code>, by default <code>~/jobhunt_docs</code>). The text and skills read
          from it are saved in the app's database.
        </li>
        <li>
          <b>Jobs and scores.</b> Jobs the app collects or you paste in, their match scores and the status you give
          them (saved, applied, rejected) are saved in a SQLite database file (<code>DATABASE_URL</code>, by default{" "}
          <code>jobhunt.db</code> in the app folder).
        </li>
        <li>
          <b>Documents you generate.</b> Cover letters, resume suggestions and backups are written to your documents
          folder.
        </li>
      </ul>
      <p>
        The app writes its log to the terminal it runs in and does not keep it. API keys are removed from log lines.
        The part of the app the browser talks to listens on this computer only (127.0.0.1), so nothing else on your
        network can reach it.
      </p>

      <h2>What leaves your computer</h2>
      <ul>
        <li>
          <b>Job searches.</b> When you press Find jobs, your search keywords, and your location where the source
          supports it, are sent to the sources you ticked (RemoteOK, Hacker News, The Muse, Arbeitnow, Himalayas,
          and any Greenhouse or Lever company boards set in <code>.env</code>). Your resume is not sent.
        </li>
        <li>
          <b>LinkedIn and Naukri, only if you turn them on.</b> When you list them in <code>.env</code>, the same
          search is sent to those sites. This is off by default.
        </li>
        <li>
          <b>Writing with a language model.</b> By default cover letters and resume suggestions are written by
          Ollama on your own computer, so your resume and the job description stay here. If you set{" "}
          <code>GEMINI_API_KEY</code> and Ollama is not available, the app sends your resume text and the job
          description to Google's Gemini API instead, and Google's terms then apply to that text. Without a key,
          nothing is sent.
        </li>
        <li>
          <b>The matching model.</b> The first time it runs, the app downloads a small open model
          (all-MiniLM-L6-v2) from Hugging Face. Only the download request is sent; your resume is not.
        </li>
        <li>
          <b>Opening a posting.</b> Open posting opens the employer's or job board's page in your browser, where
          that site's own privacy policy applies.
        </li>
      </ul>

      <h2>Deleting your data</h2>
      <p>
        Use Back up or clean up stored jobs on the Find jobs tab to delete old jobs, or delete the database file and
        the documents folder to remove everything. The app keeps no copies anywhere else. Text you sent to Gemini
        and searches you sent to job sites are held by those services under their own policies.
      </p>

      <h2>Changes</h2>
      <p>
        If the app starts handling data differently, this page is updated in the same change and the date above
        moves forward.
      </p>
    </>
  );
}

"use client";

import { useState } from "react";
import { CheckIcon } from "@/components/icons";

const profileDetails = [
  ["Name", "Alex Worker"],
  ["Role", "Web Designer"],
  ["Status", "Available"],
];

export default function ProfileCardPage() {
  const [verified, setVerified] = useState(false);

  return <div className="profile-delivery-page">
    <section className="profile-delivery-shell" aria-labelledby="profile-title">
      <header className="profile-delivery-header">
        <div>
          <p className="profile-delivery-kicker"><span aria-hidden="true"/> Public work delivery</p>
          <h1 id="profile-title">Merit Profile Card</h1>
          <p>Verified work deserves trusted payment.</p>
        </div>
        <span className="profile-delivery-badge">Bradbury testnet</span>
      </header>

      <div className="profile-card-grid">
        <article className="worker-profile-card" aria-label="Alex Worker profile">
          <div className="worker-avatar" aria-hidden="true">AW</div>
          <div className="worker-profile-copy">
            <p>Independent professional</p>
            <h2>Alex Worker</h2>
            <span><i aria-hidden="true"/> Available</span>
          </div>
          <dl>
            {profileDetails.map(([label, value]) => <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>)}
          </dl>
        </article>

        <aside className="profile-proof-card" aria-labelledby="proof-title">
          <span className="profile-proof-icon" aria-hidden="true"><CheckIcon size={22}/></span>
          <p>Delivery evidence</p>
          <h2 id="proof-title">Ready for inspection</h2>
          <ul>
            <li><CheckIcon size={15}/> Public HTTPS page</li>
            <li><CheckIcon size={15}/> Responsive layout</li>
            <li><CheckIcon size={15}/> Interactive verification</li>
          </ul>
        </aside>
      </div>

      <div className="profile-delivery-action">
        <button type="button" onClick={() => setVerified(true)}>View profile</button>
        <p className={verified ? "verified" : ""} role="status" aria-live="polite">
          {verified && <><CheckIcon size={17}/> Verification successful</>}
        </p>
      </div>

      <footer>Protected by Merit</footer>
    </section>
  </div>;
}

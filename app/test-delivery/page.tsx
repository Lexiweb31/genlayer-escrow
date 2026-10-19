"use client";

import { useState } from "react";
import { CheckIcon } from "@/components/icons";

const checklist = ["Public webpage", "Responsive layout", "Working button"];

export default function TestDeliveryPage() {
  const [verified, setVerified] = useState(false);

  return <div className="test-delivery-page">
    <section className="test-delivery-card" aria-labelledby="delivery-title">
      <div className="test-delivery-intro">
        <p className="test-delivery-kicker">Intelligent escrow deliverable</p>
        <h1 id="delivery-title">Merit Test Delivery</h1>
        <p className="test-delivery-lede">This work was completed for intelligent escrow verification.</p>
      </div>

      <section className="delivery-checklist" aria-labelledby="checklist-title">
        <h2 id="checklist-title">Delivery checklist</h2>
        <ul>{checklist.map((item) => <li key={item}><span aria-hidden="true"><CheckIcon size={18}/></span>{item}</li>)}</ul>
      </section>

      <div className="delivery-action">
        <button type="button" className="delivery-complete-button" onClick={() => setVerified(true)}>Work completed</button>
        <p className={`delivery-success ${verified ? "visible" : ""}`} role="status" aria-live="polite">{verified ? "Verification successful" : ""}</p>
      </div>

      <footer>Delivered on Bradbury</footer>
    </section>
  </div>;
}

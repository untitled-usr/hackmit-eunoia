import { useCallback, useEffect, useId, useState } from 'react'

import './eunoia-disclaimer.css'

export function EunoiaDisclaimer() {
  const [open, setOpen] = useState(false)
  const titleId = useId()

  const onClose = useCallback(() => setOpen(false), [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      <div className="eunoia-disclaimer-bar">
        <button type="button" className="eunoia-disclaimer-trigger" onClick={() => setOpen(true)}>
          Eunoia Disclaimer
        </button>
      </div>

      {open ? (
        <div
          className="eunoia-disclaimer-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose()
          }}
        >
          <div
            className="eunoia-disclaimer-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <h2 id={titleId}>DISCLAIMER</h2>
            <p className="eunoia-disclaimer-meta">Last Updated: March 28, 2026</p>

            <h2>1. NOT A MEDICAL OR THERAPEUTIC TOOL</h2>
            <p>
              The content, features, recording tools, and interactive services provided through this website
              (collectively, the &quot;Platform&quot;)—including but not limited to mood tracking,
              self-assessment questionnaires, data visualization, and related functionalities—are intended
              solely for personal use as a self-tracking and journaling aid. Their purpose is to help you
              document and reflect upon your subjective emotional experiences.
            </p>
            <p>
              The Platform does not constitute any form of medical advice, psychological treatment,
              psychiatric diagnosis, rehabilitation plan, or professional counseling. It is not a substitute
              for professional judgment, diagnosis, treatment, or intervention provided by a qualified medical
              professional, licensed mental health provider, psychiatrist, psychologist, or clinical social
              worker.
            </p>
            <p>
              You must not rely on any content or functionality of the Platform to make decisions regarding
              your physical or mental health. If you have or suspect you may have a mental health condition,
              psychiatric disorder, or any other condition requiring professional intervention—including but
              not limited to depression, anxiety disorder, bipolar disorder, post-traumatic stress disorder
              (PTSD), suicidal ideation, or self-harming behaviors—you must immediately discontinue use of the
              Platform and seek appropriate help from a licensed psychiatrist, psychologist, or other
              qualified healthcare provider in person.
            </p>

            <h2>2. EMERGENCY AND CRISIS SITUATIONS</h2>
            <p>
              If you are experiencing any of the following: suicidal thoughts, self-harm urges, plans to harm
              yourself or others, overwhelming despair, or any other acute emotional crisis, you must stop
              using the Platform immediately and take one or more of the following steps without delay:
            </p>
            <ul>
              <li>
                Call your local emergency number (e.g., 911 in the United States, 999 in the United Kingdom,
                000 in Australia, 112 in the European Union, or the appropriate emergency services in your
                country).
              </li>
              <li>
                Contact a crisis helpline or suicide prevention hotline (e.g., 988 Suicide &amp; Crisis
                Lifeline in the U.S.; Samaritans in the U.K.; Lifeline in Australia; or the crisis service
                available in your jurisdiction).
              </li>
              <li>Go to the nearest hospital emergency room.</li>
              <li>
                Reach out to a trusted family member, friend, or caregiver and ask for immediate support.
              </li>
            </ul>
            <p>
              The Platform does not provide crisis monitoring, real-time intervention, or emergency response
              services. Under no circumstances should the Platform be used as a substitute for professional
              crisis intervention.
            </p>

            <h2>3. USER RESPONSIBILITY</h2>
            <p>
              Your use of the Platform is entirely voluntary and based on your own judgment. You acknowledge
              and agree that:
            </p>
            <ul>
              <li>
                You are solely responsible for evaluating the accuracy, completeness, and relevance of any
                information you record on or obtain from the Platform.
              </li>
              <li>
                You assume all risks associated with any actions you take or refrain from taking based on
                your use of the Platform.
              </li>
              <li>
                The Platform shall not be liable for any emotional distress, delayed care, misjudgment of
                your condition, or any other consequence arising from your use of the Platform.
              </li>
              <li>
                If you are under the age of 18 (a &quot;minor&quot;), you confirm that you have reviewed this
                Disclaimer with a parent or legal guardian and that your use of the Platform is conducted
                under their supervision. Parents and guardians are solely responsible for monitoring the
                mental health and safety of any minor who uses the Platform, and they must not rely on the
                Platform as the sole means of assessing or intervening in a minor&apos;s psychological
                well-being.
              </li>
            </ul>

            <h2>4. SPECIFIC WARNING – SELF-HARM AND SUICIDE</h2>
            <p>
              The Platform expressly discourages and does not support any form of self-injury, self-harm,
              suicide, or any life-threatening behavior, regardless of the user&apos;s age, with particular
              emphasis on adolescents and minors. The self-tracking functions are offered solely to help users
              observe emotional patterns and encourage them to seek appropriate professional support. Nothing
              on the Platform is intended to suggest, encourage, normalize, or justify self-harm,
              self-injury, or suicide.
            </p>
            <p>
              If any content on the Platform (including user-generated or third-party content) could be
              interpreted in a manner inconsistent with this warning, such interpretation is unintentional,
              and the Platform disclaims any liability arising from such interpretation.
            </p>

            <h2>5. LIMITATION OF LIABILITY</h2>
            <p>
              To the fullest extent permitted by applicable law, the Platform and its operators, affiliates,
              officers, employees, partners, and content providers shall not be liable for:
            </p>
            <ul>
              <li>
                Any direct, indirect, incidental, special, consequential, or punitive damages arising out of
                or in connection with your use of, or inability to use, the Platform, including but not
                limited to worsening of mental health conditions, delayed treatment, self-harm, suicide,
                property damage, or loss of data.
              </li>
              <li>
                The accuracy, safety, or reliability of any content, links, or services provided by third
                parties that may be accessed through the Platform.
              </li>
              <li>
                Any consequences resulting from your submission of false, incomplete, or misleading
                information, or from your failure to seek timely professional help.
              </li>
            </ul>

            <h2>6. GOVERNING LAW AND DISPUTE RESOLUTION</h2>
            <p>
              This Disclaimer and any dispute arising out of or relating to your use of the Platform shall be
              governed by the laws of [Insert Jurisdiction, e.g., the State of New York / the laws of England
              and Wales / the laws of the People&apos;s Republic of China], without regard to its conflict of
              law principles. Any legal action or proceeding arising under this Disclaimer shall be brought
              exclusively in the courts located in [Insert City/Region], and the parties irrevocably consent
              to the personal jurisdiction and venue of such courts.
            </p>

            <h2>7. MODIFICATIONS AND SEVERABILITY</h2>
            <p>
              The Platform reserves the right to modify, update, or replace this Disclaimer at any time. Any
              changes will be effective immediately upon posting on the Platform. Your continued use of the
              Platform after any such modification constitutes your acceptance of the revised Disclaimer. If
              any provision of this Disclaimer is found to be invalid or unenforceable, the remaining
              provisions shall remain in full force and effect.
            </p>

            <p className="eunoia-disclaimer-closing">
              IF YOU HAVE ANY QUESTIONS ABOUT THIS DISCLAIMER, OR IF YOU BELIEVE YOU ARE IN NEED OF IMMEDIATE
              MENTAL HEALTH SUPPORT, PLEASE STOP USING THE PLATFORM AND CONTACT A QUALIFIED HEALTHCARE
              PROFESSIONAL OR CRISIS SERVICE WITHOUT DELAY. YOUR SAFETY AND WELL-BEING ARE ALWAYS MORE
              IMPORTANT THAN ANY TOOL OR APPLICATION.
            </p>

            <button type="button" className="eunoia-disclaimer-close" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      ) : null}
    </>
  )
}

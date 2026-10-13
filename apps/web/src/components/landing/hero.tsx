import Link from "next/link";
import type { CSSProperties } from "react";
import { preload } from "react-dom";
import { HeroVideo } from "./hero-video";
import styles from "./hero.module.css";

/** The headline, one entry per line. A line fits the frame up to 6.3em wide in the display face. */
export const HEADLINE = ["MEASURE", "REGRESSION", "PROVEN"];

const TAGLINE = ["Regression detection for LLM agents.", "Statistically corrected,", "flakiness-aware."];
const SERVICES = ["Repeat every case", "Judge traces and tool calls", "Gate the pull request"];
const REPO = "https://github.com/AlfredBateman/AgentProbe";
const RELEASE = "v0.1.0";

const vars = (values: Record<`--${string}`, number>) => values as CSSProperties;

/** The landing page's full-viewport hero. Its palette is scoped to it (ADR 0040). */
export function Hero() {
  preload("/hero-poster.webp", { as: "image", fetchPriority: "high" });
  const spoken = HEADLINE.join(", ").toLowerCase();
  return (
    <section className={styles.hero} style={vars({ "--n": HEADLINE.length })}>
      <div className={styles.photo} role="presentation">
        <HeroVideo />
      </div>
      <div className={styles.scrim} aria-hidden="true" />
      <div className={styles.grid} aria-hidden="true">
        {Array.from({ length: 48 }, (_, i) => (
          <i key={i} />
        ))}
      </div>

      <Link href="/" className={styles.logo} aria-label="AgentProbe, home">
        AgentProbe
      </Link>
      <p className={`${styles.tagline} ${styles.small}`}>
        {TAGLINE.map((line, i) => (
          <span key={line} style={vars({ "--i": i })}>
            {line}{" "}
          </span>
        ))}
      </p>
      <div className={`${styles.contact} ${styles.small}`}>
        <a href={REPO} style={vars({ "--i": 0 })}>
          GitHub
        </a>
        <a href={`${REPO}/releases/tag/${RELEASE}`} className={styles.badge} style={vars({ "--i": 1 })}>
          {RELEASE}
        </a>
      </div>
      <nav className={styles.actions} aria-label="Account">
        <Link href="/login">Sign in</Link>
        <Link href="/register" className={styles.menu}>
          Get started
        </Link>
      </nav>

      <ul className={`${styles.services} ${styles.small}`} aria-label="What AgentProbe does">
        {SERVICES.map((service, i) => (
          <li key={service}>
            <span className={styles.rc}>
              <span className={styles.rv} style={vars({ "--i": i })}>
                {service}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <div className={styles.rule} aria-hidden="true" />

      {/* The label is the accessible name; the lines are the same words, set for the eye. */}
      <h1 className={styles.hl} aria-label={spoken[0].toUpperCase() + spoken.slice(1)}>
        {HEADLINE.map((line, i) => (
          <span key={line} className={styles.hl__line} style={vars({ "--i": i })} aria-hidden="true">
            <span className={styles.hl__clip}>
              <span className={styles.hl__track}>{line}</span>
            </span>
          </span>
        ))}
      </h1>
    </section>
  );
}

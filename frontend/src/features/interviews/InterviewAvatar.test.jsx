import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import InterviewAvatar, { preloadInterviewAvatar } from "./InterviewAvatar.jsx";

describe("Interview avatar assets", () => {
  it("requests every pose before the first state change and only once per URL", () => {
    const OriginalImage = globalThis.Image;
    const requested = [];
    globalThis.Image = class {
      set src(value) { requested.push(value); }
      decode() { return Promise.resolve(); }
    };
    try {
      preloadInterviewAvatar();
      preloadInterviewAvatar();
      expect(requested).toEqual([
        "/avatars/interview-guide.webp",
        "/avatars/interview-guide-smile.webp",
        "/avatars/interview-guide-attentive.webp",
        "/avatars/interview-guide-blink.webp",
        "/avatars/interview-guide-thinking.webp",
        "/avatars/interview-office.webp",
      ]);
    } finally {
      globalThis.Image = OriginalImage;
    }
  });

  it("keeps the idle portrait visible until the thinking pose loads", () => {
    const { container, rerender } = render(<InterviewAvatar state="idle" />);
    const thinking = container.querySelector(".interview-avatar-thinking-pose");
    expect(thinking).toBeInTheDocument();
    rerender(<InterviewAvatar state="processing" />);
    expect(container.querySelector(".interview-avatar-portrait")).not.toHaveClass("has-thinking-pose");
    fireEvent.load(thinking);
    expect(container.querySelector(".interview-avatar-portrait")).toHaveClass("has-thinking-pose");
    expect(thinking).toHaveClass("is-visible");
  });
});

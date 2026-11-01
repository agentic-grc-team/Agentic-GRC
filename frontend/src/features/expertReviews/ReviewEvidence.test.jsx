import {
  act,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import ReviewEvidence from "./ReviewEvidence.jsx";
import { getReviewEvidence } from "./api.js";


vi.mock("./api.js", () => ({
  getReviewEvidence: vi.fn(),
}));

const emptyEvidence = {
  sources: [],
  linked_documents: [],
  evidence_pending: false,
  skipped_source_count: 0,
};

const document = {
  id: "file-1",
  original_filename: "MFA-policy.pdf",
  size_bytes: 2048,
  content_type: "application/pdf",
};


describe("ReviewEvidence", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getReviewEvidence.mockResolvedValue(emptyEvidence);
  });

  it("distinguishes attachments, document citations and interview statements", async () => {
    getReviewEvidence.mockResolvedValue({
      ...emptyEvidence,
      evidence_pending: true,
      linked_documents: [document],
      sources: [
        {
          source_type: "document_span",
          reference: "document_span:file-1#page=4",
          document: document,
          excerpt: "MFA is required.",
        },
        {
          source_type: "interview_turn",
          reference: "interview_turn:turn-1",
          excerpt: "Only some users have MFA.",
        },
      ],
    });

    render(
      <ReviewEvidence resultId="result-1" accessToken="token" />,
    );

    expect(
      await screen.findByText("MFA is required."),
    ).toBeInTheDocument();

    expect(
      screen.getByText("Only some users have MFA."),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/attestations, not documentary evidence/),
    ).toBeInTheDocument();

    expect(
      screen.getByText("Additional evidence requested."),
    ).toBeInTheDocument();

    expect(
      screen.getAllByText("MFA-policy.pdf"),
    ).toHaveLength(2);

    expect(
      screen.getByText("document_span:file-1#page=4"),
    ).toBeInTheDocument();

    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    expect(getReviewEvidence).toHaveBeenCalledWith(
      "result-1",
      "token",
    );
  });

  it("marks which interview statements come from the transcript", async () => {
    getReviewEvidence.mockResolvedValue({
      ...emptyEvidence,
      sources: [
        {
          source_type: "interview_turn",
          reference: "interview_turn:turn-1",
          excerpt: "We enforce MFA for admins only.",
          from_transcript: true,
        },
        {
          source_type: "interview_turn",
          reference: "interview_turn:turn-2",
          excerpt: "Saved only.",
          from_transcript: false,
        },
        {
          source_type: "interview_turn",
          reference: "interview_turn:turn-3",
          excerpt: null,
          from_transcript: false,
        },
      ],
    });

    render(
      <ReviewEvidence resultId="result-1" accessToken="token" />,
    );

    expect(
      await screen.findByText("We enforce MFA for admins only."),
    ).toBeInTheDocument();

    expect(
      screen.getByText("Quoted from the interview transcript."),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Saved citation, not found in this assessment/),
    ).toBeInTheDocument();

    expect(
      screen.getByText("No saved excerpt available."),
    ).toBeInTheDocument();
  });

  it("shows missing documents and malformed-source warnings", async () => {
    getReviewEvidence.mockResolvedValue({
      ...emptyEvidence,
      skipped_source_count: 1,
      sources: [
        {
          source_type: "document_span",
          reference: "document_span:missing",
          document: null,
        },
      ],
    });

    render(
      <ReviewEvidence resultId="result-1" accessToken="token" />,
    );

    expect(
      await screen.findByText(
        "Document unavailable in this assessment context",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "No documents are currently linked to this control.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "No interview sources were recorded for this result.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "Some saved source entries could not be displayed.",
      ),
    ).toBeInTheDocument();
  });

  it("distinguishes loading failure from absent evidence and supports retry", async () => {
    getReviewEvidence.mockRejectedValueOnce(
      new Error("Server unavailable"),
    );

    render(
      <ReviewEvidence resultId="result-1" accessToken="token" />,
    );

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("This does not mean evidence is absent.");

    expect(
      screen.queryByText(
        "No documents are currently linked to this control.",
      ),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry evidence" }),
    );

    expect(
      await screen.findByText(
        "No documents are currently linked to this control.",
      ),
    ).toBeInTheDocument();
  });

  it.each(["success", "failure"])(
    "ignores stale %s after the result and session change",
    async (outcome) => {
      let resolveOld;
      let rejectOld;

      getReviewEvidence.mockImplementationOnce(
        () =>
          new Promise((resolve, reject) => {
            resolveOld = resolve;
            rejectOld = reject;
          }),
      );

      const { rerender } = render(
        <ReviewEvidence
          resultId="result-old"
          accessToken="old-token"
        />,
      );

      rerender(
        <ReviewEvidence
          resultId="result-new"
          accessToken="new-token"
        />,
      );

      await screen.findByText(
        "No documents are currently linked to this control.",
      );

      await act(async () => {
        if (outcome === "success") {
          resolveOld({
            ...emptyEvidence,
            linked_documents: [document],
          });
        } else {
          rejectOld(new Error("Old request failed"));
        }
      });

      expect(
        screen.queryByText("MFA-policy.pdf"),
      ).not.toBeInTheDocument();

      expect(
        screen.queryByRole("alert"),
      ).not.toBeInTheDocument();

      expect(getReviewEvidence).toHaveBeenLastCalledWith(
        "result-new",
        "new-token",
      );
    },
  );

  it("immediately hides loaded evidence when only the token changes", async () => {
    getReviewEvidence.mockResolvedValueOnce({
      ...emptyEvidence,
      linked_documents: [document],
    });

    const { rerender } = render(
      <ReviewEvidence
        resultId="result-1"
        accessToken="old-token"
      />,
    );

    await screen.findByText("MFA-policy.pdf");

    getReviewEvidence.mockImplementationOnce(
      () => new Promise(() => {}),
    );

    rerender(
      <ReviewEvidence
        resultId="result-1"
        accessToken="new-token"
      />,
    );

    expect(
      screen.queryByText("MFA-policy.pdf"),
    ).not.toBeInTheDocument();

    expect(
      screen.getByText("Loading evidence and sources..."),
    ).toBeInTheDocument();
  });

  it("ignores the previous result's response within the same session", async () => {
    let resolveOld;

    getReviewEvidence.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );

    const { rerender } = render(
      <ReviewEvidence
        resultId="result-old"
        accessToken="token"
      />,
    );

    rerender(
      <ReviewEvidence
        resultId="result-new"
        accessToken="token"
      />,
    );

    await screen.findByText(
      "No documents are currently linked to this control.",
    );

    await act(async () => {
      resolveOld({
        ...emptyEvidence,
        linked_documents: [document],
      });
    });

    expect(
      screen.queryByText("MFA-policy.pdf"),
    ).not.toBeInTheDocument();

    expect(getReviewEvidence).toHaveBeenLastCalledWith(
      "result-new",
      "token",
    );
  });

  it("ignores a failed request after unmount", async () => {
    let rejectRequest;

    getReviewEvidence.mockImplementationOnce(
      () =>
        new Promise((resolve, reject) => {
          rejectRequest = reject;
        }),
    );

    const { unmount } = render(
      <ReviewEvidence resultId="result-1" accessToken="token" />,
    );

    unmount();

    await act(async () => {
      rejectRequest(new Error("Late failure"));
    });

    expect(
      screen.queryByRole("alert"),
    ).not.toBeInTheDocument();
  });
    it("keeps loaded evidence when the token refreshes for the same user", async () => {
      getReviewEvidence.mockResolvedValueOnce({
        ...emptyEvidence,
        linked_documents: [document],
      });

      const { rerender } = render(
        <ReviewEvidence
          resultId="result-1"
          accessToken="old-token"
          sessionId="user-1"
        />,
      );

      await screen.findByText("MFA-policy.pdf");

      rerender(
        <ReviewEvidence
          resultId="result-1"
          accessToken="new-token"
          sessionId="user-1"
        />,
      );

      expect(screen.getByText("MFA-policy.pdf")).toBeInTheDocument();
      expect(getReviewEvidence).toHaveBeenCalledTimes(1);
      expect(
        screen.queryByText("Loading evidence and sources..."),
      ).not.toBeInTheDocument();
    });

    it("uses the refreshed token when retrying", async () => {
      getReviewEvidence.mockRejectedValueOnce(
        new Error("Server unavailable"),
      );

      const { rerender } = render(
        <ReviewEvidence
          resultId="result-1"
          accessToken="old-token"
          sessionId="user-1"
        />,
      );

      await screen.findByRole("alert");

      rerender(
        <ReviewEvidence
          resultId="result-1"
          accessToken="new-token"
          sessionId="user-1"
        />,
      );

      expect(getReviewEvidence).toHaveBeenCalledTimes(1);

      fireEvent.click(
        screen.getByRole("button", { name: "Retry evidence" }),
      );

      await screen.findByText(
        "No documents are currently linked to this control.",
      );

      expect(getReviewEvidence).toHaveBeenLastCalledWith(
        "result-1",
        "new-token",
      );
    });

    it.each(["success", "failure"])(
      "ignores stale %s when the user changes for the same result",
      async (outcome) => {
        let resolveOld;
        let rejectOld;

        getReviewEvidence.mockImplementationOnce(
          () =>
            new Promise((resolve, reject) => {
              resolveOld = resolve;
              rejectOld = reject;
            }),
        );

        const { rerender } = render(
          <ReviewEvidence
            resultId="result-1"
            accessToken="old-token"
            sessionId="user-old"
          />,
        );

        rerender(
          <ReviewEvidence
            resultId="result-1"
            accessToken="new-token"
            sessionId="user-new"
          />,
        );

        await screen.findByText(
          "No documents are currently linked to this control.",
        );

        await act(async () => {
          if (outcome === "success") {
            resolveOld({
              ...emptyEvidence,
              linked_documents: [document],
            });
          } else {
            rejectOld(new Error("Old request failed"));
          }
        });

        expect(
          screen.queryByText("MFA-policy.pdf"),
        ).not.toBeInTheDocument();
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        expect(getReviewEvidence).toHaveBeenCalledTimes(2);
      },
    );

    it.each([
      [23, null, "(23 bytes)"],
      [24500, "application/pdf", "(24.5 KB, application/pdf)"],
      [2500000, null, "(2.5 MB)"],
    ])(
      "formats a document of %i bytes with content type %s",
      async (sizeBytes, contentType, expected) => {
        getReviewEvidence.mockResolvedValueOnce({
          ...emptyEvidence,
          linked_documents: [
            {
              ...document,
              size_bytes: sizeBytes,
              content_type: contentType,
            },
          ],
        });

        render(
          <ReviewEvidence resultId="result-1" accessToken="token" />,
        );

        expect(
          await screen.findByText(expected),
        ).toBeInTheDocument();
      },
    );
});
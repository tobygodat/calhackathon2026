// Lab Context settings page (handoff "Lab Context").
// Companion to the Research Dashboard welcome screen — lets a user give the
// system background about their lab: reference documents, open questions, and
// miscellaneous notes. Numbered 1-2-3 guide: each input sits beside a circled
// step number, separated by hairline dividers, in a single centred column.
import { useRef, useState } from "react";
import TopNav from "../welcome/TopNav";

// A file the user has staged for upload. We hold the File handle so Save can
// POST the actual bytes; name/size are cached for rendering the chip.
interface StagedFile {
  id: string;
  name: string;
  size: number;
  file: File;
}

// B / KB / MB — handoff §"Size formatting".
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

// Circled step number on the left rail — 34×34, faint hairline ring.
const stepBadge =
  "flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-full border-[1.5px] border-step-ring font-sans text-[15px] text-[#d8d8d8]";
const stepTitle = "font-sans text-[19px] font-medium text-primary-text mb-1";
const fieldHelper = "font-sans text-[14px] leading-[1.6] text-muted-text";
const textareaClass =
  "w-full resize-y box-border rounded-[10px] border border-field-border bg-surface px-4 py-[14px] font-sans text-[15px] leading-[1.65] text-primary-text outline-none transition-colors duration-150 placeholder:text-[#6b6f76] focus:border-[#6b6f76] focus:bg-surface-hover";

export default function LabContextPage() {
  const [uploadedFiles, setUploadedFiles] = useState<StagedFile[]>([]);
  const [openQuestions, setOpenQuestions] = useState("");
  const [miscNotes, setMiscNotes] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const staged = Array.from(files).map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random()
        .toString(36)
        .slice(2)}`,
      name: file.name,
      size: file.size,
      file,
    }));
    setUploadedFiles((prev) => [...prev, ...staged]);
  };

  const removeFile = (id: string) =>
    setUploadedFiles((prev) => prev.filter((f) => f.id !== id));

  const handleSave = () => {
    // TODO: POST files + text fields to the lab-context endpoint once it's live.
    // eslint-disable-next-line no-console
    console.log("Save lab context", {
      files: uploadedFiles.map((f) => f.file),
      openQuestions,
      miscNotes,
    });
  };

  const handleCancel = () => {
    setUploadedFiles([]);
    setOpenQuestions("");
    setMiscNotes("");
  };

  return (
    <div className="flex h-screen flex-col">
      <TopNav active="labContext" />

      <div className="flex h-[calc(100vh-56px)] bg-bg">
        {/* Main panel */}
        <main className="lc-scroll box-border flex-1 overflow-y-auto pb-20 pt-14">
          <div className="mx-auto box-border max-w-[720px] px-14">
            {/* Header */}
            <h1 className="mb-1 font-sans text-[34px] font-semibold tracking-[-0.01em] text-primary-text">
              Lab Context
            </h1>
            <p className="mb-11 font-sans text-[15px] leading-[1.6] text-muted-text">
              Three things help us flag the right papers for your lab.
            </p>

            {/* Step 1 — Upload reference documents */}
            <div className="mb-9 flex gap-[22px] border-b border-divider pb-9">
              <div className={stepBadge}>1</div>
              <div className="min-w-0 flex-1">
                <div className={stepTitle}>Upload reference documents</div>
                <p className={`${fieldHelper} mb-[18px]`}>
                  Prior papers, grant proposals, or lab notes. PDF, DOCX, or TXT.
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    addFiles(e.dataTransfer.files);
                  }}
                  className={`cursor-pointer rounded-[12px] border-[1.5px] border-dashed p-[30px] text-center transition-colors duration-200 ${
                    dragOver
                      ? "border-[#6b6f76] bg-surface-hover"
                      : "border-muted-border bg-surface hover:border-[#6b6f76] hover:bg-surface-hover"
                  }`}
                >
                  <svg
                    width="26"
                    height="26"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#c8c8c8"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="mx-auto mb-2.5"
                    aria-hidden="true"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                  <div className="font-sans text-[14px] text-[#d8d8d8]">
                    Drag files here or{" "}
                    <span className="text-primary-text underline">browse</span>
                  </div>
                </div>

                {/* File list */}
                {uploadedFiles.length > 0 && (
                  <div className="mt-3 flex flex-col gap-[7px]">
                    {uploadedFiles.map((f) => (
                      <div
                        key={f.id}
                        className="flex items-center gap-[9px] rounded-[8px] border border-field-border bg-surface px-[11px] py-2"
                      >
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="#c8c8c8"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="flex-shrink-0"
                          aria-hidden="true"
                        >
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14 2 14 8 20 8" />
                        </svg>
                        <div className="min-w-0 flex-1 truncate font-sans text-[13px] text-[#e2e2e2]">
                          {f.name}
                        </div>
                        <div className="flex-shrink-0 font-sans text-[12px] text-faint-text">
                          {formatSize(f.size)}
                        </div>
                        <button
                          type="button"
                          onClick={() => removeFile(f.id)}
                          aria-label={`Remove ${f.name}`}
                          className="flex-shrink-0 px-[2px] text-[18px] leading-none text-faint-text transition-colors hover:text-primary-text"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Step 2 — Relevant open questions */}
            <div className="mb-9 flex gap-[22px] border-b border-divider pb-9">
              <div className={stepBadge}>2</div>
              <div className="min-w-0 flex-1">
                <div className={stepTitle}>Relevant open questions</div>
                <p className={`${fieldHelper} mb-4`}>
                  List the questions your lab is actively trying to answer.
                  Papers that speak to these get prioritised.
                </p>
                <textarea
                  value={openQuestions}
                  onChange={(e) => setOpenQuestions(e.target.value)}
                  placeholder={
                    "e.g. What mechanism drives PSL energy transfer at low temperatures?\nDoes the equatorial curvature anomaly replicate across hemispheres?"
                  }
                  className={`${textareaClass} min-h-[120px]`}
                />
              </div>
            </div>

            {/* Step 3 — Anything else */}
            <div className="mb-[38px] flex gap-[22px]">
              <div className={stepBadge}>3</div>
              <div className="min-w-0 flex-1">
                <div className={stepTitle}>Anything else</div>
                <p className={`${fieldHelper} mb-4`}>
                  Collaborators, methods you favour, journals you trust, topics
                  to avoid.
                </p>
                <textarea
                  value={miscNotes}
                  onChange={(e) => setMiscNotes(e.target.value)}
                  placeholder="e.g. We collaborate closely with the Hertz lab at Stanford. Prefer empirical over purely theoretical work. Skip anything paywalled behind Elsevier."
                  className={`${textareaClass} min-h-[100px]`}
                />
              </div>
            </div>

            {/* Footer actions — aligned under the field column (34px badge + 22px gap) */}
            <div className="flex justify-end gap-3 pl-[56px]">
              <button
                type="button"
                onClick={handleCancel}
                className="rounded-[8px] border border-muted-border bg-transparent px-5 py-[9px] font-sans text-[14px] text-[#c8c8c8] transition-colors hover:border-[#6b6f76] hover:bg-surface-hover"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                className="rounded-[8px] border border-primary-text bg-primary-text px-[22px] py-[9px] font-sans text-[14px] font-medium text-bg transition-colors hover:bg-white"
              >
                Save context
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';
import { Brain, Loader2, Sparkles, FileText, ArrowRight, RotateCcw } from 'lucide-react';
import { fileApi, quizApi } from '../api';
import { QuizDifficulty, QuizResponse, UploadedFile } from '../types';

const chunkText = (text: string, targetSize = 1400, maxChunks = 18): string[] => {
  const cleaned = (text || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return [];

  const chunks: string[] = [];
  let cursor = 0;

  while (cursor < cleaned.length && chunks.length < maxChunks) {
    let end = Math.min(cursor + targetSize, cleaned.length);
    if (end < cleaned.length) {
      const breakAt = Math.max(
        cleaned.lastIndexOf('. ', end),
        cleaned.lastIndexOf('? ', end),
        cleaned.lastIndexOf('! ', end),
        cleaned.lastIndexOf('; ', end)
      );
      if (breakAt > cursor + 400) {
        end = breakAt + 1;
      }
    }
    const piece = cleaned.slice(cursor, end).trim();
    if (piece) chunks.push(piece);
    cursor = end;
  }

  return chunks;
};

const isMcqCorrect = (selected: string, correct: string): boolean => {
  const s = (selected || '').trim().toLowerCase();
  const c = (correct || '').trim().toLowerCase();
  if (!s || !c) return false;
  if (s === c) return true;

  const cLetter = c.match(/^[a-d]/)?.[0];
  const sLetter = s.match(/^[a-d]/)?.[0];
  if (cLetter && sLetter && cLetter === sLetter) return true;

  return false;
};

const Quiz: React.FC = () => {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [selectedFileMd5, setSelectedFileMd5] = useState('');
  const [focusText, setFocusText] = useState('');
  const [difficulty, setDifficulty] = useState<QuizDifficulty>('medium');
  const [questionCount, setQuestionCount] = useState(5);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<QuizResponse | null>(null);
  const [usedChunks, setUsedChunks] = useState(0);
  const [selectedOptions, setSelectedOptions] = useState<Record<number, string>>({});
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const [grades, setGrades] = useState<Record<number, number>>({});
  const [currentIndex, setCurrentIndex] = useState(0);
  const [quizFinished, setQuizFinished] = useState(false);

  const selectedFile = useMemo(
    () => files.find((f) => f.fileMd5 === selectedFileMd5) || null,
    [files, selectedFileMd5]
  );

  const loadFiles = async () => {
    try {
      setFilesLoading(true);
      const list = await fileApi.list();
      setFiles(list);
      if (!selectedFileMd5 && list.length > 0) {
        setSelectedFileMd5(list[0].fileMd5);
      }
    } catch (e) {
      console.error('Failed to load uploaded files for quiz', e);
    } finally {
      setFilesLoading(false);
    }
  };

  useEffect(() => {
    void loadFiles();
  }, []);

  const handleGenerate = async () => {
    if (!selectedFileMd5 || !selectedFile) {
      setError('Please select an uploaded file.');
      return;
    }

    try {
      setLoading(true);
      setError('');
      setResult(null);

      const contentRes = await fileApi.getContent(selectedFileMd5);
      const content = (contentRes?.content || '').trim();
      const retrievedChunks = chunkText(content);

      if (retrievedChunks.length === 0) {
        throw new Error('No readable content found in the selected file.');
      }

      const topic = focusText.trim()
        ? `${selectedFile.fileName} - ${focusText.trim()}`
        : selectedFile.fileName;

      const quiz = await quizApi.generate({
        topic,
        difficulty,
        number_of_questions: questionCount,
        bloom_level: 'understand',
        retrieved_chunks: retrievedChunks,
      });

      setUsedChunks(retrievedChunks.length);
      setResult(quiz);
      setSelectedOptions({});
      setRevealed({});
      setGrades({});
      setCurrentIndex(0);
      setQuizFinished(false);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to generate quiz.');
    } finally {
      setLoading(false);
    }
  };

  const totalQuestions = result?.questions.length || 0;
  const currentQuestion = result?.questions[currentIndex];
  const answeredCount = Object.keys(grades).length;
  const score = Object.values(grades).reduce((acc, v) => acc + v, 0);
  const maxScore = totalQuestions;
  const percentage = maxScore > 0 ? Math.round((score / maxScore) * 100) : 0;

  const canGoNext = currentQuestion
    ? Boolean(selectedOptions[currentIndex])
    : false;

  const getAssessment = (pct: number): string => {
    if (pct >= 85) return 'Excellent grasp. You can move to harder practice.';
    if (pct >= 70) return 'Good understanding. Review a few weak spots and retry.';
    if (pct >= 50) return 'Moderate understanding. Revisit core concepts in this file.';
    return 'Needs reinforcement. Re-read the file and retake the quiz.';
  };

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900">Quiz Generator</h1>
          <p className="text-neutral-500 mt-1">Select one uploaded file and generate a quiz from that file only.</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-neutral-200 p-6 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="text-sm text-neutral-700 font-medium">Source File</label>
              <p className="text-xs text-neutral-500 mt-1">Upload the file to the Knowledge Base first.</p>
              <div className="mt-1 flex items-center gap-2">
                <select
                  value={selectedFileMd5}
                  onChange={(e) => setSelectedFileMd5(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm outline-none focus:border-neutral-500 bg-white"
                >
                  {files.length === 0 ? (
                    <option value="">No uploaded files</option>
                  ) : (
                    files.map((f) => (
                      <option key={f.fileMd5} value={f.fileMd5}>
                        {f.fileName}
                      </option>
                    ))
                  )}
                </select>
                <button
                  type="button"
                  onClick={() => void loadFiles()}
                  disabled={filesLoading}
                  className="px-3 py-2 rounded-xl border border-neutral-300 text-sm text-neutral-700 hover:bg-neutral-50 disabled:opacity-60"
                >
                  {filesLoading ? 'Loading...' : 'Refresh'}
                </button>
              </div>
              {selectedFile && (
                <div className="mt-2 text-xs text-neutral-500 inline-flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  Using file: {selectedFile.fileName}
                </div>
              )}
            </div>

            <div>
              <label className="text-sm text-neutral-700 font-medium">Difficulty</label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as QuizDifficulty)}
                className="mt-1 w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm outline-none focus:border-neutral-500 bg-white"
              >
                <option value="easy">easy</option>
                <option value="medium">medium</option>
                <option value="hard">hard</option>
              </select>
            </div>

            <div>
              <label className="text-sm text-neutral-700 font-medium">Number of Questions</label>
              <input
                type="number"
                min={1}
                max={20}
                value={questionCount}
                onChange={(e) => setQuestionCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                className="mt-1 w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm outline-none focus:border-neutral-500"
              />
            </div>

            <div className="md:col-span-2">
              <label className="text-sm text-neutral-700 font-medium">Focus (optional)</label>
              <input
                value={focusText}
                onChange={(e) => setFocusText(e.target.value)}
                placeholder="e.g., key formulas and practical applications"
                className="mt-1 w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm outline-none focus:border-neutral-500"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-neutral-900 text-white text-sm hover:bg-neutral-800 disabled:opacity-60"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {loading ? 'Generating...' : 'Generate Quiz'}
            </button>
            {usedChunks > 0 && !loading && (
              <span className="text-xs text-neutral-500">Used {usedChunks} retrieved chunks</span>
            )}
          </div>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
              {error}
            </div>
          )}
        </div>

        {result && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-neutral-200 p-5">
              <div className="flex items-center gap-2 text-neutral-900 font-semibold">
                <Brain className="w-5 h-5" />
                {result.quiz_title}
              </div>
              <div className="text-xs text-neutral-500 mt-1">
                Difficulty: {result.difficulty} | Progress: {answeredCount}/{totalQuestions}
              </div>
            </div>

            {quizFinished ? (
              <div className="bg-white rounded-2xl border border-neutral-200 p-5 space-y-4">
                <h3 className="text-lg font-semibold text-neutral-900">Quiz Complete</h3>
                <div className="text-sm text-neutral-700">
                  Final Score: <span className="font-semibold">{score.toFixed(1)}/{maxScore}</span> ({percentage}%)
                </div>
                <div className="text-sm text-neutral-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                  Assessment: {getAssessment(percentage)}
                </div>

                <div className="pt-1">
                  <h4 className="text-sm font-semibold text-neutral-900 mb-2">Answer Summary</h4>
                  <div className="space-y-2">
                    {result.questions.map((q, idx) => (
                      <div key={idx} className="border border-neutral-200 rounded-lg p-3 text-sm">
                        <div className="font-medium text-neutral-900">{idx + 1}. {q.question}</div>
                        <div className="text-neutral-700 mt-1">Your answer: {selectedOptions[idx] || 'Not answered'}</div>
                        <div className="text-neutral-700">Correct answer: {q.correct_answer || '-'}</div>
                        <div className={grades[idx] === 1 ? 'text-emerald-700 mt-1' : 'text-red-700 mt-1'}>
                          Result: {grades[idx] === 1 ? 'Correct' : 'Incorrect'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setCurrentIndex(0);
                    setQuizFinished(false);
                  }}
                  className="inline-flex items-center gap-2 text-sm px-3 py-2 rounded-lg border border-neutral-300 text-neutral-700 hover:bg-neutral-50"
                >
                  <RotateCcw className="w-4 h-4" />
                  Review Flashcards
                </button>
              </div>
            ) : (
              currentQuestion && (
                <div className="bg-white rounded-2xl border border-neutral-200 p-5 space-y-3">
                  <div className="text-xs text-neutral-500">
                    {currentQuestion.type} | Card {currentIndex + 1} of {totalQuestions}
                  </div>
                  <h3 className="text-base font-semibold text-neutral-900">
                    {currentQuestion.question}
                  </h3>

                  {currentQuestion.options && (
                    <div className="space-y-2">
                      {currentQuestion.options.map((opt, i) => (
                        <label
                          key={i}
                          className="flex items-start gap-2 text-sm text-neutral-700 border border-neutral-200 rounded-lg px-3 py-2 cursor-pointer"
                        >
                          <input
                            type="radio"
                            name={`q-${currentIndex}`}
                            checked={selectedOptions[currentIndex] === opt}
                            onChange={() =>
                              setSelectedOptions((prev) => ({ ...prev, [currentIndex]: opt }))
                            }
                            className="mt-0.5"
                          />
                          <span>{opt}</span>
                        </label>
                      ))}

                      {!revealed[currentIndex] && (
                        <button
                          type="button"
                          disabled={!selectedOptions[currentIndex]}
                          onClick={() => {
                            const correct = isMcqCorrect(
                              selectedOptions[currentIndex],
                              currentQuestion.correct_answer || ''
                            );
                            setRevealed((prev) => ({ ...prev, [currentIndex]: true }));
                            setGrades((prev) => ({ ...prev, [currentIndex]: correct ? 1 : 0 }));
                          }}
                          className="text-sm px-3 py-2 rounded-lg bg-neutral-900 text-white disabled:opacity-60"
                        >
                          Check Answer
                        </button>
                      )}

                      {revealed[currentIndex] && currentQuestion.correct_answer && (
                        <>
                          <div
                            className={
                              grades[currentIndex] === 1
                                ? 'text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2'
                                : 'text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2'
                            }
                          >
                            {grades[currentIndex] === 1 ? 'Correct' : 'Incorrect'}
                          </div>
                          <div className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                            Correct answer: {currentQuestion.correct_answer}
                          </div>
                          <div className="text-sm text-neutral-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                            {currentQuestion.explanation}
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      disabled={!canGoNext}
                      onClick={() => {
                        if (grades[currentIndex] === undefined) {
                          const correct = isMcqCorrect(
                            selectedOptions[currentIndex],
                            currentQuestion.correct_answer || ''
                          );
                          setGrades((prev) => ({ ...prev, [currentIndex]: correct ? 1 : 0 }));
                        }
                        if (currentIndex < totalQuestions - 1) {
                          setCurrentIndex((prev) => prev + 1);
                        } else {
                          setQuizFinished(true);
                        }
                      }}
                      className="inline-flex items-center gap-2 text-sm px-3 py-2 rounded-lg bg-neutral-900 text-white disabled:opacity-60"
                    >
                      {currentIndex < totalQuestions - 1 ? 'Next' : 'Finish'}
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Quiz;

package com.papervision;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.dao.DataAccessException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/question-bank")
@CrossOrigin(origins = {"http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:5174"})
public class QuestionBankController {
    private final QuestionBankService service;

    public QuestionBankController(QuestionBankService service) { this.service = service; }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @PostMapping("/imports")
    public ImportResult importQuestions(@RequestBody ImportRequest request) {
        if (request.questions() == null || request.questions().isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "至少需要一题");
        }
        return service.importQuestions(request);
    }

    public record ImportRequest(List<QuestionInput> questions, RelaInput rela) {}
    public record QuestionInput(String content, Integer questionType, Integer difficultyLevel,
                                String correctAnswer, String answerAnalysis, Long gradeId,
                                Long subjectId, List<String> imagePaths, List<OptionInput> options) {}
    public record OptionInput(String label, String content, List<String> imagePaths) {}
    public record RelaInput(Long stageId, Long gradeId, Long subjectId, Long editionId, Integer xueqiId) {}
    public record ImportResult(List<Long> questionIds, int insertedCount) {}

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> handleBusinessError(ResponseStatusException ex) {
        String detail = ex.getReason() == null || ex.getReason().isBlank() ? "题库写入失败" : ex.getReason();
        return ResponseEntity.status(ex.getStatusCode()).body(Map.of("detail", detail));
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<Map<String, String>> handleDatabaseError(DataAccessException ex) {
        String message = ex.getMostSpecificCause() == null ? ex.getMessage() : ex.getMostSpecificCause().getMessage();
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("detail", "数据库写入失败：" + message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleAll(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Map.of("detail", ex.getClass().getSimpleName() + ": " + ex.getMessage()));
    }
}

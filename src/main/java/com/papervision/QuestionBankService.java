package com.papervision;

import com.papervision.QuestionBankController.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.*;

@Service
public class QuestionBankService {
    private final JdbcTemplate jdbc;
    private final String codeid;
    private final long deptId;
    private final String username;

    public QuestionBankService(JdbcTemplate jdbc,
        @Value("${paper-vision.owner.codeid}") String codeid,
        @Value("${paper-vision.owner.dept-id}") long deptId,
        @Value("${paper-vision.owner.username}") String username) {
        this.jdbc = jdbc; this.codeid = codeid; this.deptId = deptId; this.username = username;
    }

    @Transactional
    public ImportResult importQuestions(ImportRequest request) {
        List<QuestionInput> questions = request.questions();
        RelaInput rela = request.rela();
        List<Long> ids = new ArrayList<>();
        for (QuestionInput question : questions) {
            long questionId = insertOne(question);
            insertRela(questionId, rela);
            ids.add(questionId);
        }
        return new ImportResult(ids, ids.size());
    }

    private void insertRela(long questionId, RelaInput rela) {
        if (rela == null || rela.stageId() == null || rela.gradeId() == null || rela.subjectId() == null) return;
        jdbc.update(
            "INSERT INTO nine_question_bank_rela (question_id,stage_id,grade_id,subject_id,edition_id,xueqi_id) VALUES (?,?,?,?,?,?)",
            questionId, rela.stageId(), rela.gradeId(), rela.subjectId(),
            rela.editionId() == null ? 0L : rela.editionId(),
            rela.xueqiId() == null ? 1 : rela.xueqiId()
        );
    }

    private long insertOne(QuestionInput q) {
        require(q.content() != null && !q.content().isBlank(), "题干不能为空");
        require(q.questionType() != null && q.questionType() >= 0 && q.questionType() <= 4, "题型不合法");
        require(q.difficultyLevel() != null && q.difficultyLevel() >= 0 && q.difficultyLevel() <= 4, "难度不合法");
        List<OptionInput> options = q.options() == null ? List.of() : q.options();
        if (q.questionType() <= 1) require(!options.isEmpty(), "选择题必须有选项");
        String normalized = q.content().replaceAll("\\s+", " ").trim();
        String md5 = md5(normalized);
        String storedContent = appendImages(q.content(), q.imagePaths(), "题目图像");
        Integer existing = jdbc.queryForObject("SELECT COUNT(*) FROM nine_question_bank WHERE md5_str=? AND del_flag=1", Integer.class, md5);
        require(existing == null || existing == 0, "题库中已存在相同题干，已取消写入");

        KeyHolder holder = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var ps = connection.prepareStatement("""
                INSERT INTO nine_question_bank (parent_id,question_content,grade_id,subject_id,question_type,difficulty_level,correct_answer,answer_analysis,sort,create_time,codeid,dept_id,create_by,update_by,content_type,del_flag,score,game_type,status,ftype,sj_id,md5_str)
                VALUES (0,?,?,?,?,?,?,?,?,?,?,?,?,?,1,1,0,0,1,'0',NULL,?)
                """, java.sql.Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, storedContent); ps.setObject(2, q.gradeId()); ps.setObject(3, q.subjectId());
            ps.setInt(4, q.questionType()); ps.setInt(5, q.difficultyLevel()); ps.setString(6, blankToNull(q.correctAnswer()));
            ps.setString(7, blankToNull(q.answerAnalysis())); ps.setInt(8, 0); ps.setObject(9, LocalDateTime.now());
            ps.setString(10, codeid); ps.setLong(11, deptId); ps.setString(12, username); ps.setString(13, username); ps.setString(14, md5);
            return ps;
        }, holder);
        Number key = holder.getKey();
        if (key == null) throw new IllegalStateException("数据库未返回 question_id");
        long id = key.longValue();
        Set<String> labels = new HashSet<>();
        for (int i = 0; i < options.size(); i++) {
            OptionInput option = options.get(i);
            String label = option.label() == null ? "" : option.label().trim().toUpperCase();
            require(label.matches("[A-Z]{1,10}") && labels.add(label), "选项标签必须唯一且为字母");
            require(option.content() != null && !option.content().isBlank(), "选项内容不能为空");
            String optionContent = appendImages(option.content(), option.imagePaths(), "选项图像");
            jdbc.update("INSERT INTO nine_question_option (question_id,option_label,option_content,sort,del_flag) VALUES (?,?,?,?,1)", id, label, optionContent, i);
        }
        return id;
    }

    private static void require(boolean valid, String message) { if (!valid) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message); }
    private static String blankToNull(String value) { return value == null || value.isBlank() ? null : value; }
    private void requireSafeImagePath(String path) {
        require(path != null && path.matches("/uploads/graphs/[a-f0-9]{32}/[a-zA-Z0-9-]+\\.jpg"), "图片地址不合法");
    }
    private String appendImages(String content, List<String> imagePaths, String alt) {
        if (imagePaths == null || imagePaths.isEmpty()) return content;
        StringBuilder stored = new StringBuilder(content);
        for (String path : imagePaths) {
            requireSafeImagePath(path);
            stored.append("<div class=\"question-image\"><img src=\"")
                .append(path).append("\" alt=\"").append(alt).append("\"></div>");
        }
        return stored.toString();
    }
    private static String md5(String value) { try { byte[] d=MessageDigest.getInstance("MD5").digest(value.getBytes(StandardCharsets.UTF_8)); StringBuilder b=new StringBuilder(); for(byte x:d)b.append(String.format("%02x",x)); return b.toString(); } catch(Exception e) { throw new IllegalStateException(e); } }
}

package com.pbl4.studentweb.user.mapper;

import com.pbl4.studentweb.user.entity.User;
import com.pbl4.studentweb.user.dto.UserSummary;
import org.springframework.stereotype.Component;
@Component
public class UserMapper {
    public UserSummary toSummary(User u) {
        return new UserSummary(u.getId(), u.getUsername(), u.getRole(), u.isEnabled(), u.isPasswordSetupRequired());
    }
}

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-signup',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './signup.component.html',
  styleUrls: ['./signup.component.css'],
})
export class SignupComponent {
  mode: 'join' | 'create' = 'join';

  username = '';
  email = '';
  password = '';
  confirmPassword = '';
  inviteCode = '';
  companyName = '';

  error = '';
  loading = false;
  success = false;

  showPassword = false;
  showConfirm = false;
  showInvite = false;

  constructor(private auth: AuthService) {}

  setMode(mode: 'join' | 'create') {
    this.mode = mode;
    this.error = '';
  }

  async onSubmit() {
    this.error = '';
    if (this.password !== this.confirmPassword) {
      this.error = 'Passwords do not match.';
      return;
    }
    this.loading = true;
    try {
      if (this.mode === 'join') {
        await this.auth.register(this.username, this.email, this.password, this.confirmPassword, this.inviteCode);
      } else {
        await this.auth.registerCompany(this.companyName, this.username, this.email, this.password, this.confirmPassword);
      }
      this.success = true;
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Registration failed. Please try again.';
    } finally {
      this.loading = false;
    }
  }
}

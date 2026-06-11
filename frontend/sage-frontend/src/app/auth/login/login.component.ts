import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
})
export class LoginComponent {
  username = '';
  password = '';
  error = '';
  loading = false;
  showPassword = false;

  constructor(private auth: AuthService, private router: Router) {}

  async onSubmit() {
    this.error = '';
    this.loading = true;
    try {
      await this.auth.login(this.username, this.password);
      this.router.navigate(['/accounts']);
    } catch {
      this.error = 'Invalid username or password.';
    } finally {
      this.loading = false;
    }
  }
}

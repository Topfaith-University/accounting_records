import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';

@Component({
  selector: 'app-customer-statement',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './customer-statement.component.html',
})
export class CustomerStatementComponent implements OnInit {
  statement: any = null;
  loading = true;
  error = '';

  private id = '';

  constructor(private route: ActivatedRoute, private receivables: ReceivablesService) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      this.statement = await this.receivables.getCustomerStatement(this.id);
    } catch {
      this.error = 'Failed to load customer statement.';
    } finally {
      this.loading = false;
    }
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.receivables.exportCustomerStatement(this.id, format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
